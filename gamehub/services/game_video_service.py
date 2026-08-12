"""WEBM → MP4 conversion via ffmpeg.

The recording itself happens client-side in the admin's own browser
(see api/routes/recorder.py) — this module only converts the resulting
WEBM clip to a 640x360 H.264 MP4 that Telegram can preview and that the
game card sends via answer_video.

NOTE: this module used to also drive a headless Playwright/Chromium
session on the server to record gameplay. That approach could never
show the game on the admin's phone (Chromium was running invisibly on
the server, not on the admin's device), so it has been removed in favor
of the browser-side recorder page. ffmpeg is the only remaining external
dependency here.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360


async def convert_recorded_video_to_mp4(
    source: Path,
    destination: Path,
) -> Path:
    """
    WEBM recordingni 640x360 MP4 ga aylantiradi.
    """

    source = Path(source)
    destination = Path(destination)

    if not source.exists():
        raise FileNotFoundError(
            f"Video topilmadi: {source}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(source),

        "-vf",
        (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "(ow-iw)/2:"
            "(oh-ih)/2"
        ),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(destination),
    ]

    logger.info(
        "[GAME VIDEO] Converting WEBM → MP4: %s",
        destination,
    )

    process = (
        await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    )

    _, stderr = (
        await process.communicate()
    )

    if process.returncode != 0:

        error = stderr.decode(
            "utf-8",
            errors="replace",
        )

        logger.error(
            "[GAME VIDEO] FFmpeg error: %s",
            error[-3000:],
        )

        raise RuntimeError(
            "WEBM → MP4 conversion failed."
        )

    if not destination.exists():
        raise RuntimeError(
            "MP4 yaratilmadi."
        )

    if destination.stat().st_size < 1024:
        raise RuntimeError(
            "MP4 fayl juda kichik yoki bo'sh."
        )

    logger.info(
        "[GAME VIDEO] MP4 created: %s",
        destination,
    )

    return destination
