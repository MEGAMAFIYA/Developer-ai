"""File download helpers — fetches Telegram files and writes them to disk."""

import logging
import io
from pathlib import Path

from aiogram import Bot

logger = logging.getLogger(__name__)

# Root webapp directory (gamehub/webapp/)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
GAMES_DIR = WEBAPP_DIR / "games"
ASSETS_DIR = WEBAPP_DIR / "assets" / "games"


# Telegram image mime-type → file extension
_MIME_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

ALLOWED_IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
}

ALLOWED_IMAGE_MIME = frozenset(_MIME_EXT)


def image_ext_from_filename_or_mime(
    filename: str | None,
    mime: str | None,
    *,
    fallback: str = ".jpg",
) -> str | None:
    """Resolve a safe image extension from Telegram metadata."""

    normalized_mime = (mime or "").lower().split(";", 1)[0].strip()
    suffix = Path(filename or "").suffix.lower()

    if normalized_mime not in ALLOWED_IMAGE_MIME:
        return None

    ext = (
        ".gif"
        if normalized_mime == "image/gif"
        else suffix
        if suffix in ALLOWED_IMAGE_EXTS
        else _MIME_EXT[normalized_mime]
    )

    return ".jpg" if ext == ".jpeg" else ext


def ensure_dirs() -> None:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


async def save_html(bot: Bot, file_id: str, slug: str) -> Path:
    """Download an HTML document from Telegram and save as webapp/games/{slug}.html."""

    ensure_dirs()

    dest = GAMES_DIR / f"{slug}.html"

    file_info = await bot.get_file(file_id)

    await bot.download_file(
        file_info.file_path,
        destination=str(dest),
    )

    logger.info("HTML saved: %s", dest)

    return dest


async def save_image(
    bot: Bot,
    file_id: str,
    slug: str,
    ext: str,
) -> Path:
    """
    Download an image/animation from Telegram and save it.

    IMPORTANT:
    The downloaded bytes are NOT inspected or rejected.
    The extension supplied by the caller is used as-is.
    """

    ensure_dirs()

    ext = ext if ext.startswith(".") else f".{ext}"

    dest = ASSETS_DIR / f"{slug}{ext}"

    file_info = await bot.get_file(file_id)

    buffer = io.BytesIO()

    await bot.download_file(
        file_info.file_path,
        destination=buffer,
    )

    content = buffer.getvalue()

    # Intentionally NO image-signature validation here.
    # Telegram animation/GIF uploads are allowed through without
    # checking whether the downloaded bytes begin with GIF/PNG/JPEG/etc.
    dest.write_bytes(content)

    logger.info(
        "Image/animation saved without byte validation: %s",
        dest,
    )

    return dest


def save_html_bytes(
    slug: str,
    content: bytes,
) -> Path:
    """
    Persist HTML bytes in the runtime WebApp directory.

    This is a runtime-serving copy only. Developer/AI project-source
    reads and writes go through the GitHub project provider.
    """

    ensure_dirs()

    dest = GAMES_DIR / f"{slug}.html"

    dest.write_bytes(content)

    logger.info(
        "Runtime HTML saved: %s",
        dest,
    )

    return dest


def save_image_bytes(
    slug: str,
    ext: str,
    content: bytes,
) -> Path:
    """
    Persist image/animation bytes in the runtime asset directory.

    No byte/signature validation is performed.
    """

    ensure_dirs()

    ext = ext if ext.startswith(".") else f".{ext}"

    dest = ASSETS_DIR / f"{slug}{ext}"

    # Intentionally no validation.
    dest.write_bytes(content)

    logger.info(
        "Runtime image/animation saved without byte validation: %s",
        dest,
    )

    return dest


def ext_from_mime(
    mime: str | None,
    fallback: str = ".jpg",
) -> str:
    """Return a file extension for the given MIME type."""

    return _MIME_EXT.get(
        mime or "",
        fallback,
    )


def image_db_url(
    slug: str,
    ext: str,
) -> str:
    """Return the image_url value stored in the database."""

    ext = ext if ext.startswith(".") else f".{ext}"

    return f"/webapp/assets/games/{slug}{ext}"