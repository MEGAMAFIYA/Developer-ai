"""AI Developer — shared action logger for Phase 4 tools.

Every destructive or mutating AI action is appended to
logs/ai_actions.log inside the gamehub directory.

Format (one line per action):
    [YYYY-MM-DD HH:MM:SS] admin=<id> | <ACTION> | <details> | <result>

Usage:
    from handlers.developer.modules.ai.action_log import log_action
    await log_action(query.from_user.id, "FILE_EDIT", "webapp/games/snake.html", "ok")
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# gamehub/logs/ai_actions.log
_BASE    = Path(__file__).resolve().parents[4]   # gamehub/
_LOG_DIR = _BASE / "logs"
_LOG_FILE = _LOG_DIR / "ai_actions.log"


async def log_action(
    admin_id: int,
    action: str,
    details: str,
    result: str,
) -> None:
    """Append one structured line to ai_actions.log (non-blocking I/O)."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        det  = details[:300].replace("\n", " ")
        res  = result[:200].replace("\n", " ")
        line = f"[{ts}] admin={admin_id} | {action} | {det} | {res}\n"
        await asyncio.to_thread(_write, _LOG_FILE, line)
    except Exception as exc:
        logger.warning("action_log write failed: %s", exc)


async def read_recent(n: int = 30) -> str:
    """Return the last *n* lines of the log file as a plain string."""
    try:
        if not _LOG_FILE.exists():
            return "Log fayli hali yaratilmagan."
        lines = await asyncio.to_thread(_tail, _LOG_FILE, n)
        return "".join(lines) or "Log bo'sh."
    except Exception as exc:
        return f"Log o'qishda xato: {exc}"


# ── Sync helpers (run in thread) ──────────────────────────────────────────────

def _write(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _tail(path: Path, n: int) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return f.readlines()[-n:]
