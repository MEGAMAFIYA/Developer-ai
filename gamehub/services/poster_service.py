"""Static poster (JPEG) generation for animated game thumbnails.

Telegram's `InlineQueryResultArticle.thumbnail_url` only renders reliably
when it points to a static JPEG — pointing it directly at a `.gif` or
`.mp4` file causes the preview to silently disappear in the inline
results list. To keep the exact list-style picker (thumbnail + title +
description) working for GIF/MP4 games too, we extract a single static
frame with ffmpeg the first time it's needed and cache it on disk next
to the source file, e.g.:

    webapp/assets/games/domboqchalar.gif
    webapp/assets/games/domboqchalar.gif.poster.jpg   ← generated, cached

Every call after the first is a free disk-existence check.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

POSTER_SUFFIX = ".poster.jpg"


def poster_path_for(source: Path) -> Path:
    """Where the cached poster for `source` lives (may not exist yet)."""

    return source.with_name(source.name + POSTER_SUFFIX)


async def get_or_create_poster(source: Path) -> Path | None:
    """
    Return a static JPEG poster for a GIF/MP4 asset, generating and
    caching it on first use via ffmpeg. Returns None if generation
    fails (caller should fall back gracefully).
    """

    source = Path(source)

    if not source.exists() or not source.is_file():
        logger.warning("[POSTER] Source not found: %s", source)
        return None

    poster = poster_path_for(source)

    # Already cached — and not stale (source wasn't re-uploaded since).
    if (
        poster.exists()
        and poster.stat().st_mtime >= source.stat().st_mtime
    ):
        return poster

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(poster),
    ]

    logger.info("[POSTER] Generating poster for %s", source)

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(
                "[POSTER] ffmpeg failed for %s: %s",
                source,
                stderr.decode("utf-8", errors="replace")[-1500:],
            )
            return None

        if not poster.exists() or poster.stat().st_size < 100:
            logger.error("[POSTER] Poster not created (or empty): %s", poster)
            return None

        return poster

    except Exception as exc:
        logger.error("[POSTER] Unexpected error for %s: %s", source, exc)
        return None
