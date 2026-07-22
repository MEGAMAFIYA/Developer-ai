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
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# gamehub/logs/ai_actions.log
# parents[4] of  gamehub/handlers/developer/modules/ai/action_log.py  → gamehub/
_BASE     = Path(__file__).resolve().parents[4]
_LOG_DIR  = _BASE / "logs"
_LOG_FILE = _LOG_DIR / "ai_actions.log"

# ── Thread safety ─────────────────────────────────────────────────────────────
# A single lock shared across all asyncio.to_thread calls so concurrent
# log_action coroutines never interleave partial writes.
_write_lock = threading.Lock()

# ── Create log directory once at import time (fast no-op if it exists) ────────
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception as _exc:                        # pragma: no cover
    logger.warning("action_log: cannot create log dir %s: %s", _LOG_DIR, _exc)


# ── Public API ────────────────────────────────────────────────────────────────

async def log_action(
    admin_id: int,
    action: str,
    details: str,
    result: str,
) -> None:
    """Append one structured line to ai_actions.log (non-blocking, thread-safe)."""
    try:
        ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        det = str(details)[:300].replace("\n", " ")
        res = str(result)[:200].replace("\n", " ")
        line = f"[{ts}] admin={admin_id} | {action} | {det} | {res}\n"
        await asyncio.to_thread(_write, _LOG_FILE, line)
    except Exception as exc:
        logger.warning("action_log write failed: %s", exc)


async def read_recent(n: int = 30) -> str:
    """Return the last *n* lines of the log file as a plain string.

    Never raises — returns an informational message on any error.
    """
    try:
        if not _LOG_FILE.exists():
            return "Log fayli hali yaratilmagan."
        lines = await asyncio.to_thread(_tail, _LOG_FILE, n)
        return "".join(lines) or "Log bo'sh."
    except Exception as exc:
        logger.warning("action_log read failed: %s", exc)
        return f"Log o'qishda xato: {exc}"


async def clear_log() -> tuple[bool, str]:
    """Truncate ai_actions.log to zero bytes.

    Returns (success: bool, message: str).
    Never raises.
    """
    try:
        if not _LOG_FILE.exists():
            return True, "Log fayli mavjud emas."
        size = _LOG_FILE.stat().st_size
        await asyncio.to_thread(_truncate, _LOG_FILE)
        return True, f"{size:,} bayt bo'shatildi."
    except Exception as exc:
        logger.warning("action_log clear failed: %s", exc)
        return False, f"Xato: {exc}"


# ── Sync helpers (run inside asyncio.to_thread) ───────────────────────────────

def _write(path: Path, line: str) -> None:
    """Append *line* to *path* under the write lock — thread-safe."""
    with _write_lock:
        # Ensure log dir still exists (e.g. after a clear-logs operation)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def _tail(path: Path, n: int) -> list[str]:
    """Return the last *n* lines of *path* efficiently.

    Uses a backward seek so large files are not fully loaded into memory.
    Falls back to a full read for files smaller than the seek chunk.
    """
    CHUNK = 32_768  # 32 KB — covers ~50+ typical log lines
    with open(path, "rb") as f:
        f.seek(0, 2)                    # seek to end
        file_size = f.tell()
        if file_size == 0:
            return []

        buf      = b""
        found    = 0
        pos      = file_size

        while pos > 0 and found < n + 1:
            read_size = min(CHUNK, pos)
            pos      -= read_size
            f.seek(pos)
            buf  = f.read(read_size) + buf
            found = buf.count(b"\n")

    lines = buf.decode("utf-8", errors="replace").splitlines(keepends=True)
    # Drop a leading empty partial line that can appear at position 0
    if lines and not lines[0].endswith("\n"):
        lines = lines[1:]
    return lines[-n:]


def _truncate(path: Path) -> None:
    with _write_lock:
        with open(path, "w", encoding="utf-8"):
            pass
