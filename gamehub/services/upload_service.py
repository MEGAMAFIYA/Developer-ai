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


def mirror_runtime_write(repo_path: str, content: bytes) -> Path | None:
    """Mirror a GitHub commit onto the locally-served copy, if applicable.

    ``gamehub/api/app.py`` serves games (and ``/webapp/...`` static assets)
    straight off local disk — it never reads GitHub at request time. So a
    GitHub-only write (Developer/AI file tools) would be real and permanent,
    but invisible on the *running* bot until the next Render deploy pulls a
    fresh checkout.

    This mirrors any write that lands under the live ``gamehub/webapp/``
    tree onto the same local path save_html_bytes()/save_image_bytes() use,
    so the change is visible immediately. Returns the local path written,
    or None if ``repo_path`` falls outside the served webapp tree (e.g. a
    Python source file — those only ever need the GitHub commit).
    """
    prefix = "gamehub/webapp/"
    normalized = repo_path.strip().lstrip("/")
    if not normalized.startswith(prefix):
        return None
    rel = normalized[len(prefix):]
    if not rel or ".." in rel.split("/"):
        return None
    dest = WEBAPP_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    logger.info("Runtime mirror write: %s -> %s", repo_path, dest)
    return dest


def mirror_runtime_delete(repo_path: str) -> Path | None:
    """Delete the locally-served mirror of a GitHub-deleted file, if any.

    Counterpart to mirror_runtime_write() — see its docstring for why this
    is needed. Returns the local path removed, or None if there was
    nothing to remove (outside the served tree, or already absent).
    """
    prefix = "gamehub/webapp/"
    normalized = repo_path.strip().lstrip("/")
    if not normalized.startswith(prefix):
        return None
    rel = normalized[len(prefix):]
    if not rel or ".." in rel.split("/"):
        return None
    dest = WEBAPP_DIR / rel
    if dest.exists():
        dest.unlink()
        logger.info("Runtime mirror delete: %s -> %s", repo_path, dest)
        return dest
    return None


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