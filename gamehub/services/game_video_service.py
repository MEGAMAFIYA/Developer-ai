from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_DIR = (
    BASE_DIR
    / "webapp"
    / "generated_videos"
)

DEFAULT_DURATION = 12

VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360


# ============================================================
# DIRECTORY
# ============================================================

def _ensure_dirs() -> None:
    """
    MP4/WebM fayllari saqlanadigan papkani yaratadi.
    """
    VIDEO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

# ============================================================
# GAME VIDEO SESSION
# ============================================================

async def create_game_mp4(
    slug: str,
    html_bytes: bytes,
    duration: int = DEFAULT_DURATION,
) -> Path:
    """
    Chromium orqali o'yinni ochib, MP4 yaratadi.

    Hozircha bu funksiya avtomatik AI o'yinchi
    ishlatmaydi. Keyingi qismda recording va
    gameplay boshqaruvi ulanadi.
    """

    _ensure_dirs()

    duration = max(
        3,
        min(int(duration), 60),
    )

    mp4_path = (
        VIDEO_DIR
        / f"{slug}.mp4"
    )

    logger.info(
        "[GAME VIDEO] Preparing: %s",
        slug,
    )

    # Keyingi qismda:
    # - HTML o'yinni ochish
    # - 640x360 recording
    # - Start tugmasi
    # - qo'lda o'ynash
    # - recording boshlash/to'xtatish
    # - WEBM → MP4
    # jarayonlari shu funksiyaga ulanadi.

    raise NotImplementedError(
        "Game video recording session "
        "is not connected yet."
    )

# ============================================================
# WEBM → MP4
# ============================================================

async def convert_recorded_video_to_mp4(
    source: Path,
    destination: Path,
) -> Path:
    """
    Qo'lda yozib olingan WEBM videoni
    640x360 MP4 formatiga aylantiradi.
    """

    _ensure_dirs()

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

        # ====================================================
        # 640x360
        # ====================================================

        "-vf",
        (
            "scale=640:360:"
            "force_original_aspect_ratio=decrease,"
            "pad=640:360:"
            "(ow-iw)/2:"
            "(oh-ih)/2"
        ),

        # ====================================================
        # MP4
        # ====================================================

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
        "[GAME VIDEO] Converting recording → MP4: %s",
        destination,
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

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


# ============================================================
# SAVE RECORDED VIDEO
# ============================================================

async def save_recorded_video(
    slug: str,
    source: Path,
) -> Path:
    """
    Foydalanuvchi yozib olgan videoni
    yakuniy MP4 sifatida saqlaydi.
    """

    _ensure_dirs()

    mp4_path = (
        VIDEO_DIR
        / f"{slug}.mp4"
    )

    return await convert_recorded_video_to_mp4(
        source,
        mp4_path,
    )


# ============================================================
# VIDEO PATH
# ============================================================

def get_video_path(
    slug: str,
) -> Path:
    """
    O'yinning tayyor MP4 fayli manzilini qaytaradi.
    """

    _ensure_dirs()

    return (
        VIDEO_DIR
        / f"{slug}.mp4"
    )