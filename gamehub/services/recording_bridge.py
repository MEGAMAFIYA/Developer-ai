"""In-memory bridge between the browser recorder page and the Telegram bot.

The FastAPI process and the aiogram bot run in the same asyncio event loop
(see main.py), so a module-level dict is enough to hand a finished WEBM
recording from the `POST /api/recording/upload` route back to the
`/yangi` FSM flow in handlers/admin.py — no database or extra service needed.

Lifecycle of one token:
    1. admin.py:  create_session(...)          -> token
    2. browser:   POST /api/recording/upload    -> mark_uploaded(...)
    3. admin.py:  background poll task notices status == "uploaded"
    4. admin.py:  pop_session(...) once the WEBM has been consumed
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Recording sessions older than this are considered abandoned.
SESSION_TTL_SECONDS = 30 * 60


@dataclass
class RecordingSession:
    token: str
    user_id: int
    chat_id: int
    slug: str
    status: str = "pending"  # pending -> uploaded | error
    webm_path: Path | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)


_SESSIONS: dict[str, RecordingSession] = {}


def _sweep_expired() -> None:
    """Drop sessions older than SESSION_TTL_SECONDS and remove their temp files."""

    now = time.time()

    expired = [
        token
        for token, session in _SESSIONS.items()
        if now - session.created_at > SESSION_TTL_SECONDS
    ]

    for token in expired:
        session = _SESSIONS.pop(token, None)

        if session and session.webm_path:
            try:
                session.webm_path.unlink(missing_ok=True)
            except Exception:
                pass

        logger.info("[RECORDING BRIDGE] Expired session swept: %s", token)


def create_session(user_id: int, chat_id: int, slug: str) -> str:
    """Create a new pending recording session and return its token."""

    _sweep_expired()

    token = uuid.uuid4().hex

    _SESSIONS[token] = RecordingSession(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        slug=slug,
    )

    logger.info(
        "[RECORDING BRIDGE] Session created: token=%s user=%s slug=%s",
        token,
        user_id,
        slug,
    )

    return token


def get_session(token: str) -> RecordingSession | None:
    return _SESSIONS.get(token)


def mark_uploaded(token: str, webm_path: Path) -> bool:
    session = _SESSIONS.get(token)

    if not session:
        return False

    session.status = "uploaded"
    session.webm_path = webm_path

    logger.info(
        "[RECORDING BRIDGE] Marked uploaded: token=%s path=%s",
        token,
        webm_path,
    )

    return True


def mark_error(token: str, error: str) -> bool:
    session = _SESSIONS.get(token)

    if not session:
        return False

    session.status = "error"
    session.error = error

    return True


def pop_session(token: str) -> RecordingSession | None:
    return _SESSIONS.pop(token, None)


def cancel_sessions_for_user(user_id: int) -> None:
    """Remove any pending/uploaded sessions for a user and their temp files.

    Called when the admin restarts or cancels /yangi so no orphaned
    tokens or temporary WEBM files are left behind.
    """

    stale = [
        token
        for token, session in _SESSIONS.items()
        if session.user_id == user_id
    ]

    for token in stale:
        session = _SESSIONS.pop(token, None)

        if session and session.webm_path:
            try:
                session.webm_path.unlink(missing_ok=True)
            except Exception:
                pass

        logger.info(
            "[RECORDING BRIDGE] Session cancelled for user: token=%s",
            token,
        )
