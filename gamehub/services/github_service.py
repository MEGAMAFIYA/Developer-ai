"""Compatibility facade for ``/yangi`` GitHub uploads.

The shared ``project_provider`` is the only GitHub project-source provider.
This module keeps the existing service entry point while accepting the
Telegram-uploaded bytes directly, so the runtime filesystem is never used as
the source of a GitHub project write.
"""

from __future__ import annotations

import logging

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