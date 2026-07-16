"""POST /api/scores — validate Telegram WebApp initData and save score."""

import hashlib
import hmac
import json
import logging
import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import config
from database.game_db import save_score
from services.diamond_service import award_for_score

logger = logging.getLogger(__name__)
router = APIRouter()


class ScorePayload(BaseModel):
    game: str
    score: int
    init_data: str  # raw Telegram WebApp initData string


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
    chat_id    = int(chat.get("id", 0))
    chat_title = chat.get("title", "")

    result = await save_score(
        user_id    = user_id,
        username   = username,
        first_name = first_name,
        game_name  = payload.game,
        score      = payload.score,
        chat_id    = chat_id,
        chat_title = chat_title,
    )

    # Diamond hook — no-op until DIAMONDS_ENABLED = True
    diamonds_earned = await award_for_score(
        user_id    = user_id,
        username   = username,
        first_name = first_name,
        game_name  = payload.game,
        score      = payload.score,
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
