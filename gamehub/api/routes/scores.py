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

logger = logging.getLogger(__name__)
router = APIRouter()


class ScorePayload(BaseModel):
    game: str
    score: int
    init_data: str  # raw Telegram WebApp initData string


def _validate_init_data(init_data: str) -> dict:
    """Validate via HMAC-SHA256; returns parsed user dict."""
    params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)

    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in init_data")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid init_data signature")

    try:
        return json.loads(params.get("user", "{}"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed user data")


@router.post("/scores")
async def post_score(payload: ScorePayload) -> dict:
    if payload.score < 0:
        raise HTTPException(status_code=400, detail="Score cannot be negative")

    user = _validate_init_data(payload.init_data)
    user_id: int = user.get("id", 0)
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    record = await save_score(
        user_id=user_id,
        username=user.get("username", ""),
        first_name=user.get("first_name", ""),
        game_name=payload.game,
        score=payload.score,
    )
    logger.info("Score saved: user=%s game=%s score=%s", user_id, payload.game, payload.score)
    return {"ok": True, "id": record["id"]}
