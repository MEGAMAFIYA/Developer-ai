"""Compatibility facade for ``/yangi`` GitHub uploads.

The shared ``project_provider`` is the only GitHub project-source provider.
This module keeps the existing service entry point while accepting the
Telegram-uploaded bytes directly, so the runtime filesystem is never used as
the source of a GitHub project write.
"""

from __future__ import annotations

import logging

from services.upload_service import image_db_url
from services.project_provider import ProjectProviderError, get_project_provider

logger = logging.getLogger(__name__)

async def push_game_files(
    slug: str,
    html_content: bytes,
    image_content: bytes,
    image_ext: str = ".jpg",
) -> tuple[bool, str]:
    """Upload both new-game assets through the shared GitHub project provider."""
    image_ext = image_ext if image_ext.startswith(".") else f".{image_ext}"
    commit_message = f"Add game: {slug}"
    try:
        provider = get_project_provider()
        await provider.put_file(
            f"webapp/games/{slug}.html",
            html_content,
            commit_message,
        )
        await provider.put_file(
            f"webapp/assets/games/{slug}{image_ext}",
            image_content,
            commit_message,
        )
        logger.info("[GITHUB API] Upload OK: slug=%s", slug)
        return True, f"{commit_message} | HTML va IMAGE yuklandi"
    except ProjectProviderError as exc:
        logger.error("[GITHUB API] Upload failed: %s", exc)
        return False, str(exc)
    except Exception as exc:
        logger.exception("[GITHUB API] Unexpected error: %s", exc)
        return False, f"GitHub API kutilmagan xatosi: {exc}"


async def push_game_html(
    slug: str,
    html_content: bytes,
) -> tuple[bool, str]:
    """Update one existing game's HTML through the shared project provider."""
    commit_message = f"Update game: {slug}"
    path = f"webapp/games/{slug}.html"
    try:
        provider = get_project_provider()
        try:
            current_content, _ = await provider.get_file_bytes(path)
        except FileNotFoundError:
            current_content = None

        if current_content == html_content:
            logger.info("[GITHUB API] HTML unchanged: slug=%s", slug)
            return True, f"{commit_message} | o'zgarish yo'q"

        await provider.put_file(path, html_content, commit_message)
        logger.info("[GITHUB API] HTML update OK: slug=%s", slug)
        return True, commit_message
    except ProjectProviderError as exc:
        logger.error("[GITHUB API] HTML update failed: %s", exc)
        return False, str(exc)
    except Exception as exc:
        logger.exception("[GITHUB API] Unexpected HTML update error: %s", exc)
        return False, f"GitHub API kutilmagan xatosi: {exc}"


async def push_game_image(
    slug: str,
    image_content: bytes,
    image_ext: str,
) -> tuple[bool, str]:
    """Update/create the cover asset at the same path used by the game card."""
    image_url = image_db_url(slug, image_ext)
    path = f"webapp{image_url.removeprefix('/webapp')}"
    commit_message = f"Update game image: {slug}"
    try:
        await get_project_provider().put_file(path, image_content, commit_message)
        logger.info("[GITHUB API] Image update OK: slug=%s path=%s", slug, path)
        return True, commit_message
    except ProjectProviderError as exc:
        logger.error("[GITHUB API] Image update failed: slug=%s path=%s: %s", slug, path, exc)
        return False, str(exc)
    except Exception as exc:
        logger.exception("[GITHUB API] Unexpected image update error: slug=%s", slug)
        return False, f"GitHub API kutilmagan xatosi: {exc}"