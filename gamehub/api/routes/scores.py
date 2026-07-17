"""POST /api/scores — validate Telegram WebApp initData and save score."""

import hashlib
import hmac
import json
import logging
import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import config
from database.game_db import (
    save_score,
    verify_score_in_db,
    get_global_leaderboard,
    get_game_pool,
)
from database.global_db import ensure_game_exists
from services.diamond_service import award_for_score

logger = logging.getLogger(__name__)
router = APIRouter()


class ScorePayload(BaseModel):
    game: str
    score: int
    init_data: str        # raw Telegram WebApp initData string
    chat_id: int = 0      # group chat_id embedded in the WebApp URL by the bot (?cid=)


def _validate_init_data(init_data: str) -> tuple[dict, dict]:
    """Validate via HMAC-SHA256.

    Returns (user_dict, chat_dict) parsed from the validated initData.
    Raises HTTPException on invalid / missing data.
    """
    params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)

    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in init_data")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed   = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(status_code=401, detail="Invalid init_data signature")

    try:
        user = json.loads(params.get("user", "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed user data")

    try:
        # chat is present when the WebApp is opened from a group chat
        chat = json.loads(params.get("chat", "{}"))
    except json.JSONDecodeError:
        chat = {}

    return user, chat


@router.post("/scores")
async def post_score(payload: ScorePayload) -> dict:
    if payload.score < 0:
        raise HTTPException(status_code=400, detail="Score cannot be negative")

    user, chat = _validate_init_data(payload.init_data)

    user_id: int = user.get("id", 0)
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    username   = user.get("username", "")
    first_name = user.get("first_name", "")
    # Prefer explicit chat_id embedded in the WebApp URL (?cid=) by the bot.
    # This is the only reliable way to get the group ID when the WebApp is
    # opened via an inline keyboard button (initData.chat is only set for
    # attachment-menu launches, not for web_app keyboard buttons).
    if payload.chat_id:
        chat_id    = payload.chat_id
        chat_title = chat.get("title", "")   # may be empty; that's fine
    else:
        chat_id    = int(chat.get("id", 0))
        chat_title = chat.get("title", "")

    logger.info(
        "E2E RECV: user=%s (@%s) game=%s score=%s chat=%s",
        user_id, username, payload.game, payload.score, chat_id,
    )

    # Auto-register the game in the catalog on first score submission.
    await ensure_game_exists(payload.game)

    result = await save_score(
        user_id    = user_id,
        username   = username,
        first_name = first_name,
        game_name  = payload.game,
        score      = payload.score,
        chat_id    = chat_id,
        chat_title = chat_title,
    )

    # Read-back verification: confirm the score actually persisted in the DB.
    # Only runs for new records (i.e. rows that were actually inserted).
    if result["is_new_record"]:
        verified = await verify_score_in_db(user_id, payload.game, payload.score)
        if not verified:
            logger.error(
                "Score save verification FAILED — row missing after INSERT: "
                "user=%s game=%s score=%s",
                user_id, payload.game, payload.score,
            )
            raise HTTPException(
                status_code=500,
                detail="Score save verification failed — row not found after INSERT",
            )

    # Diamond hook — no-op until DIAMONDS_ENABLED = True
    diamonds_earned = await award_for_score(
        user_id       = user_id,
        username      = username,
        first_name    = first_name,
        game_name     = payload.game,
        score         = payload.score,
        is_new_record = result["is_new_record"],
        rank          = result["rank"],
    )

    logger.info(
        "Score processed: user=%s game=%s score=%s new_record=%s rank=%s diamonds=%s",
        user_id, payload.game, payload.score,
        result["is_new_record"], result["rank"], diamonds_earned,
    )

    return {
        "ok":            True,
        "id":            result["row"]["id"] if result["row"] else None,
        "is_new_record": result["is_new_record"],
        "previous_best": result["previous_best"],
        "rank":          result["rank"],
        "diamonds":      diamonds_earned,
    }


# ---------------------------------------------------------------------------
# Dev pipeline test — only available when DEVELOPER_MODE=True
# GET /api/scores/pipeline-test?game=snake&score=9999
# Inserts a synthetic score, reads it back, snapshots the leaderboard,
# then deletes the test row.  Returns pipeline_ok: true/false.
# ---------------------------------------------------------------------------

@router.get("/scores/pipeline-test")
async def pipeline_test(game: str = "snake", score: int = 9999) -> dict:
    if not config.DEVELOPER_MODE:
        raise HTTPException(status_code=403, detail="Developer mode is disabled")

    TEST_USER_ID    = 999_000_000
    TEST_USERNAME   = "dev_pipeline_test"
    TEST_FIRST_NAME = "DevTest"

    steps: dict = {}

    await ensure_game_exists(game)
    steps["1_game_registered"] = True

    pool = await get_game_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM scores WHERE user_id=$1 AND game_name=$2",
            TEST_USER_ID, game,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO scores
                (user_id, username, first_name, game_name, score, chat_id, chat_title)
            VALUES ($1, $2, $3, $4, $5, 0, 'PipelineTest')
            RETURNING *
            """,
            TEST_USER_ID, TEST_USERNAME, TEST_FIRST_NAME, game, score,
        )
        steps["2_inserted"] = {"id": row["id"], "score": row["score"]}

        verified = await conn.fetchrow("SELECT * FROM scores WHERE id=$1", row["id"])
        steps["3_read_back_ok"] = verified is not None
        if verified:
            steps["3_read_back_row"] = {"id": verified["id"], "score": verified["score"]}

        lb_rows = await conn.fetch(
            """
            SELECT user_id, username, first_name, MAX(score) AS best_score
            FROM scores WHERE game_name=$1
            GROUP BY user_id, username, first_name
            ORDER BY best_score DESC LIMIT 5
            """,
            game,
        )
        steps["4_leaderboard_top5"] = [
            {"name": r["first_name"] or r["username"], "score": r["best_score"]}
            for r in lb_rows
        ]

        await conn.execute("DELETE FROM scores WHERE id=$1", row["id"])
        steps["5_cleanup_ok"] = True

    steps["pipeline_ok"] = steps.get("3_read_back_ok", False)
    logger.info("Pipeline test for game='%s': %s", game, steps)
    return steps
