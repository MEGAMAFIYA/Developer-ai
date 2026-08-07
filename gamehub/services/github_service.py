"""GitHub Contents API upload service for ``/yangi`` game uploads.

The public interface intentionally remains compatible with the existing
handler:

    push_game_files(slug, html_path, image_path) -> (ok: bool, message: str)

This service uses GitHub's REST Contents API directly. It does not require a
local Git executable, a ``.git`` directory, or a Git working tree.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import aiohttp

from config import config

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_API_VERSION = "2022-11-28"
_REQUEST_TIMEOUT = 30


def _repository_path(local_path: Path) -> str:
    """Convert a local gamehub path to the repository-relative API path.

    Render may check out the project under a different absolute directory
    (for example ``/app``), so no absolute filesystem path is sent to GitHub.
    The repository layout is explicitly rooted at ``gamehub/``.
    """
    resolved = local_path.resolve()
    parts = resolved.parts
    try:
        gamehub_index = parts.index("gamehub")
    except ValueError:
        # Keep compatibility with callers that already pass a repository path.
        return local_path.as_posix().lstrip("/")
    return Path(*parts[gamehub_index:]).as_posix()


def _api_url(path: str) -> str:
    return (
        f"{_API_BASE}/repos/{config.GITHUB_OWNER}/"
        f"{config.GITHUB_REPO.rstrip('.git')}/contents/{path}"
    )


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "X-GitHub-Api-Version": _API_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "GameHub-Bot",
    }


def _response_body_preview(body: str) -> str:
    """Return a useful, bounded error body without exposing credentials."""
    return body[:1000] if body else "(bo'sh javob)"


async def _get_existing_sha(
    session: aiohttp.ClientSession,
    path: str,
) -> tuple[str | None, str | None]:
    """Read a file's SHA before updating it.

    Returns ``(sha, None)`` for an existing file, ``(None, None)`` for a
    missing file, or ``(None, error)`` for an unexpected API failure.
    """
    url = _api_url(path)
    params = {"ref": config.GITHUB_BRANCH} if config.GITHUB_BRANCH else None
    logger.info(
        "[GITHUB API] URL=%s owner=%s repo=%s branch=%s path=%s",
        url,
        config.GITHUB_OWNER,
        config.GITHUB_REPO,
        config.GITHUB_BRANCH,
        path,
    )
    async with session.get(url, headers=_headers(), params=params) as response:
        body = await response.text(encoding="utf-8", errors="replace")
        logger.info("[GITHUB API] HTTP status GET %s: %s", path, response.status)

        if response.status == 200:
            try:
                data = json.loads(body)
            except json.JSONDecodeError as exc:
                error = f"SHA javobini o'qishda xato: {exc}"
                logger.error("[GITHUB API] Response body on error: %s", _response_body_preview(body))
                return None, error
            sha = data.get("sha")
            if not sha:
                error = "GitHub javobida fayl SHA topilmadi"
                logger.error("[GITHUB API] Response body on error: %s", _response_body_preview(body))
                return None, error
            return sha, None

        if response.status == 404:
            return None, None

        logger.error("[GITHUB API] Response body on error: %s", _response_body_preview(body))
        return None, f"SHA olishda HTTP {response.status}: {_response_body_preview(body)}"


async def _upload_file(
    session: aiohttp.ClientSession,
    *,
    local_path: Path,
    repository_path: str,
    commit_message: str,
    label: str,
) -> tuple[bool, str]:
    """Create or update one repository file through the Contents API."""
    try:
        file_bytes = local_path.read_bytes()
    except OSError as exc:
        message = f"{label} faylini o'qib bo'lmadi: {exc}"
        logger.error("[GITHUB API] Response body on error: %s", message)
        return False, message

    sha, sha_error = await _get_existing_sha(session, repository_path)
    if sha_error:
        return False, sha_error

    payload: dict[str, str] = {
        "message": commit_message,
        "content": base64.b64encode(file_bytes).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    if config.GITHUB_BRANCH:
        payload["branch"] = config.GITHUB_BRANCH

    url = _api_url(repository_path)
    logger.info(
        "[GITHUB API] URL=%s owner=%s repo=%s branch=%s path=%s",
        url,
        config.GITHUB_OWNER,
        config.GITHUB_REPO,
        config.GITHUB_BRANCH,
        repository_path,
    )
    async with session.put(url, headers=_headers(), json=payload) as response:
        body = await response.text(encoding="utf-8", errors="replace")
        logger.info("[GITHUB API] HTTP status PUT %s: %s", repository_path, response.status)

        if response.status in (200, 201):
            logger.info("[GITHUB API] Upload %s OK", label)
            return True, body

        logger.error("[GITHUB API] Response body on error: %s", _response_body_preview(body))
        return False, f"{label} upload HTTP {response.status}: {_response_body_preview(body)}"


async def push_game_files(
    slug: str,
    html_path: Path,
    image_path: Path,
) -> tuple[bool, str]:
    """Upload the new game's HTML and image through GitHub Contents API.

    Each successful Contents API PUT creates the corresponding GitHub commit.
    The shared commit message is ``Add game: {slug}``; after both uploads
    succeed, the service reports the operation as committed.
    """
    if not config.GITHUB_TOKEN or not config.GITHUB_OWNER or not config.GITHUB_REPO:
        message = "GITHUB_TOKEN, GITHUB_OWNER yoki GITHUB_REPO sozlanmagan"
        logger.error("[GITHUB API] Response body on error: %s", message)
        return False, message

    if not html_path.exists():
        message = f"HTML fayl topilmadi: {html_path}"
        logger.error("[GITHUB API] Response body on error: %s", message)
        return False, message
    if not image_path.exists():
        message = f"IMAGE fayl topilmadi: {image_path}"
        logger.error("[GITHUB API] Response body on error: %s", message)
        return False, message

    html_repo_path = _repository_path(html_path)
    image_repo_path = _repository_path(image_path)
    commit_message = f"Add game: {slug}"

    logger.info(
        "[GITHUB API] Upload START: slug=%s html=%s image=%s",
        slug,
        html_repo_path,
        image_repo_path,
    )

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            html_ok, html_result = await _upload_file(
                session,
                local_path=html_path,
                repository_path=html_repo_path,
                commit_message=commit_message,
                label="HTML",
            )
            if not html_ok:
                return False, html_result

            image_ok, image_result = await _upload_file(
                session,
                local_path=image_path,
                repository_path=image_repo_path,
                commit_message=commit_message,
                label="IMAGE",
            )
            if not image_ok:
                return False, image_result

            logger.info("[GITHUB API] Commit OK: %s", commit_message)
            return True, f"{commit_message} | HTML va IMAGE yuklandi"
    except aiohttp.ClientError as exc:
        message = f"GitHub API tarmoq xatosi: {exc}"
        logger.error("[GITHUB API] Response body on error: %s", message)
        return False, message
    except TimeoutError:
        message = f"GitHub API timeout: {_REQUEST_TIMEOUT} soniya"
        logger.error("[GITHUB API] Response body on error: %s", message)
        return False, message
    except Exception as exc:
        logger.exception("[GITHUB API] Unexpected error: %s", exc)
        return False, f"GitHub API kutilmagan xatosi: {exc}"