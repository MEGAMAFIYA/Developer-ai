"""POST /api/recording/upload — receive a browser-recorded WEBM clip.

The recorder page (see api/routes/recorder.py) records the admin's own
gameplay client-side via canvas.captureStream() + MediaRecorder, then
uploads the resulting WEBM blob here as a raw request body (no multipart
dependency required). The bytes are written to a temp file and the
matching recording_bridge session is marked "uploaded" so the bot's
background poll task can pick it up and continue the /yangi flow.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from services.recording_bridge import get_session, mark_uploaded

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "webapp"
    / "recording_uploads"
)

# Reject absurdly large uploads before they hit disk (50 MB is well above
# what a short gameplay clip at 640x360 needs, and matches the Bot API's
# own upload ceiling for videos sent by a bot).
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/recording/upload")
async def upload_recording(token: str, request: Request) -> dict:
    session = get_session(token)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Recording session topilmadi yoki muddati o'tgan.",
        )

    content = await request.body()

    if not content:
        raise HTTPException(status_code=400, detail="Video fayl bo'sh.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Video fayl juda katta (50MB dan kichik bo'lishi kerak).",
        )

    if len(content) < 1024:
        raise HTTPException(
            status_code=400,
            detail="Video fayl juda kichik yoki buzilgan.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    dest = UPLOAD_DIR / f"{token}.webm"

    try:
        dest.write_bytes(content)
    except Exception as exc:
        logger.exception("Failed to write recording upload: %s", exc)
        raise HTTPException(status_code=500, detail="Faylni saqlashda xato.")

    mark_uploaded(token, dest)

    logger.info(
        "[RECORDING UPLOAD] Received: token=%s slug=%s size=%d",
        token,
        session.slug,
        len(content),
    )

    return {"ok": True}
