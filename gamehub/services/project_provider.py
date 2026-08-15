"""GitHub-backed project source for Developer Mode and AI Developer.

This module is the only project-file abstraction used by Developer features.
The running Render checkout is intentionally not consulted for project data.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import posixpath
import re
import time
import zipfile
from dataclasses import dataclass

import aiohttp

import config as cfg
from database.global_db import get_setting

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_API_VERSION = "2022-11-28"
_CACHE_TTL = 60.0
_REQUEST_TIMEOUT = 30
_MAX_SEARCH_HITS = 100
_MAX_FILE_BYTES = 8 * 1024 * 1024


class ProjectProviderError(RuntimeError):
    """Raised when the configured GitHub project cannot be accessed."""


@dataclass(slots=True)
class RepositoryFile:
    path: str
    content: str
    sha: str
    size: int


@dataclass(slots=True)
class RepositoryEntry:
    path: str
    kind: str
    size: int = 0
    sha: str = ""


class GitHubProjectProvider:
    """Read and mutate the configured GitHub repository through REST APIs."""

    def __init__(self) -> None:
        self._tree_cache: tuple[float, list[RepositoryEntry]] | None = None
        self._file_cache: dict[str, tuple[float, RepositoryFile]] = {}

    async def _settings(self) -> dict[str, str]:
        values = {
            "owner": cfg.config.GITHUB_OWNER,
            "repo": cfg.config.GITHUB_REPO,
            "branch": cfg.config.GITHUB_BRANCH or "main",
            "token": cfg.config.GITHUB_TOKEN,
        }
        for key, setting_key in (
            ("owner", "github_owner"),
            ("repo", "github_repo"),
            ("branch", "github_branch"),
        ):
            value = await get_setting(setting_key)
            if value:
                values[key] = value.strip()
        values["repo"] = values["repo"].removesuffix(".git")
        if not values["owner"] or not values["repo"] or not values["token"]:
            raise ProjectProviderError(
                "GitHub loyiha sozlamalari to'liq emas: owner, repo va token kerak."
            )
        return values

    async def _session(self) -> tuple[aiohttp.ClientSession, dict[str, str]]:
        settings = await self._settings()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings['token']}",
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "GameHub-Developer",
        }
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            headers=headers,
        ), settings

    @staticmethod
    def normalize_path(path: str, *, preserve_repository_root: bool = False) -> str:
        value = (path or "").strip().replace("\\", "/")
        if not preserve_repository_root:
            value = value.removeprefix("gamehub/").lstrip("/")
        normalized = posixpath.normpath(value)
        if not value or normalized in ("", ".", "..") or normalized.startswith("../"):
            raise ProjectProviderError("Noto'g'ri repository yo'li.")
        return normalized

    @staticmethod
    def _safe_path(path: str, *, preserve_repository_root: bool = False) -> str:
        return GitHubProjectProvider.normalize_path(
            path,
            preserve_repository_root=preserve_repository_root,
        )

    @staticmethod
    def _url(settings: dict[str, str], suffix: str) -> str:
        return (
            f"{_API_BASE}/repos/{settings['owner']}/{settings['repo']}/{suffix}"
        )

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        **kwargs,
    ) -> tuple[int, str]:
        async with session.request(method, url, **kwargs) as response:
            body = await response.text(encoding="utf-8", errors="replace")
            return response.status, body

    async def repository_label(self) -> str:
        settings = await self._settings()
        return f"{settings['owner']}/{settings['repo']}@{settings['branch']}"

    async def recent_commits(self, limit: int = 10) -> list[dict]:
        """Return recent commits from the configured branch."""
        session, settings = await self._session()
        try:
            status, body = await self._request(
                session,
                "GET",
                self._url(settings, "commits"),
                params={"sha": settings["branch"], "per_page": str(max(1, min(limit, 50)))},
            )
        finally:
            await session.close()
        if status != 200:
            raise ProjectProviderError(f"GitHub commits HTTP {status}: {body[:400]}")
        try:
            payload = json.loads(body)
            return payload if isinstance(payload, list) else []
        except (ValueError, TypeError) as exc:
            raise ProjectProviderError(f"GitHub commits javobi noto'g'ri: {exc}") from exc

    async def repository_status(self) -> dict:
        """Return branch and repository metadata without inspecting local disk."""
        session, settings = await self._session()
        try:
            status, body = await self._request(
                session,
                "GET",
                self._url(settings, ""),
            )
        finally:
            await session.close()
        if status != 200:
            raise ProjectProviderError(f"GitHub repository HTTP {status}: {body[:400]}")
        try:
            payload = json.loads(body)
        except (ValueError, TypeError) as exc:
            raise ProjectProviderError(f"GitHub repository javobi noto'g'ri: {exc}") from exc
        return {
            "owner": settings["owner"],
            "repo": settings["repo"],
            "branch": settings["branch"],
            "default_branch": payload.get("default_branch", settings["branch"]),
            "html_url": payload.get("html_url", ""),
            "open_issues": payload.get("open_issues_count", 0),
            "updated_at": payload.get("updated_at", ""),
        }

    async def clear_cache(self) -> None:
        self._tree_cache = None
        self._file_cache.clear()

    async def refresh(self) -> list[RepositoryEntry]:
        await self.clear_cache()
        return await self.tree()

    async def tree(self, force: bool = False) -> list[RepositoryEntry]:
        now = time.monotonic()
        if not force and self._tree_cache and now - self._tree_cache[0] < _CACHE_TTL:
            return list(self._tree_cache[1])

        session, settings = await self._session()
        try:
            url = self._url(
                settings,
                f"git/trees/{settings['branch']}",
            )
            status, body = await self._request(
                session,
                "GET",
                url,
                params={"recursive": "1"},
            )
        finally:
            await session.close()
        if status != 200:
            raise ProjectProviderError(f"GitHub tree HTTP {status}: {body[:400]}")
        try:
            payload = json.loads(body)
            entries = [
                RepositoryEntry(
                    path=item["path"],
                    kind="file" if item.get("type") == "blob" else "dir",
                    size=int(item.get("size") or 0),
                    sha=item.get("sha", ""),
                )
                for item in payload.get("tree", [])
                if item.get("type") in ("blob", "tree")
            ]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProjectProviderError(f"GitHub tree javobi noto'g'ri: {exc}") from exc
        self._tree_cache = (now, entries)
        return list(entries)

    async def list_files(
        self,
        folder: str = "",
        *,
        preserve_repository_root: bool = False,
    ) -> list[RepositoryEntry]:
        prefix = folder.strip().strip("/")
        if not preserve_repository_root:
            prefix = prefix.removeprefix("gamehub/")
        entries = await self.tree()
        if not prefix:
            return entries
        prefix = prefix + "/"
        return [entry for entry in entries if entry.path.startswith(prefix)]

    async def get_file(
        self,
        path: str,
        force: bool = False,
        *,
        preserve_repository_root: bool = False,
    ) -> RepositoryFile:
        normalized = self._safe_path(
            path,
            preserve_repository_root=preserve_repository_root,
        )
        now = time.monotonic()
        cached = self._file_cache.get(normalized)
        if not force and cached and now - cached[0] < _CACHE_TTL:
            return cached[1]

        session, settings = await self._session()
        try:
            url = self._url(settings, f"contents/{normalized}")
            status, body = await self._request(
                session,
                "GET",
                url,
                params={"ref": settings["branch"]},
            )
        finally:
            await session.close()
        if status == 404:
            raise FileNotFoundError(normalized)
        if status != 200:
            raise ProjectProviderError(f"GitHub fayl HTTP {status}: {body[:400]}")
        try:
            payload = json.loads(body)
            encoded = payload.get("content", "").replace("\n", "")
            raw = base64.b64decode(encoded) if encoded else b""
            if len(raw) > _MAX_FILE_BYTES:
                raise ProjectProviderError("Fayl hajmi ruxsat etilgan chegaradan katta.")
            content = raw.decode("utf-8", errors="replace")
            result = RepositoryFile(
                path=normalized,
                content=content,
                sha=payload["sha"],
                size=int(payload.get("size") or len(raw)),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ProjectProviderError(f"GitHub fayl javobi noto'g'ri: {exc}") from exc
        self._file_cache[normalized] = (now, result)
        return result

    async def get_file_bytes(
        self,
        path: str,
        *,
        preserve_repository_root: bool = False,
    ) -> tuple[bytes, str]:
        """Fetch a file's exact raw bytes (binary-safe).

        Unlike ``get_file()``, this never round-trips through UTF-8 text —
        it re-fetches the raw base64 payload straight from the GitHub API,
        so PDFs, images and other binary assets come back byte-for-byte
        intact instead of being corrupted by a lossy text decode/re-encode.
        """
        normalized = self._safe_path(
            path,
            preserve_repository_root=preserve_repository_root,
        )
        session, settings = await self._session()
        try:
            status, body = await self._request(
                session,
                "GET",
                self._url(settings, f"contents/{normalized}"),
                params={"ref": settings["branch"]},
            )
        finally:
            await session.close()
        if status == 404:
            raise FileNotFoundError(normalized)
        if status != 200:
            raise ProjectProviderError(f"GitHub fayl HTTP {status}: {body[:400]}")
        try:
            payload = json.loads(body)
            encoded = payload.get("content", "").replace("\n", "")
            raw = base64.b64decode(encoded) if encoded else b""
            if len(raw) > _MAX_FILE_BYTES:
                raise ProjectProviderError("Fayl hajmi ruxsat etilgan chegaradan katta.")
            sha = payload["sha"]
        except (KeyError, ValueError, TypeError) as exc:
            raise ProjectProviderError(f"GitHub fayl javobi noto'g'ri: {exc}") from exc
        return raw, sha

    async def put_file(
        self,
        path: str,
        content: str | bytes,
        message: str,
        *,
        sha: str | None = None,
        preserve_repository_root: bool = False,
    ) -> dict:
        normalized = self._safe_path(
            path,
            preserve_repository_root=preserve_repository_root,
        )
        if sha is None:
            try:
                sha = (
                    await self.get_file(
                        normalized,
                        force=True,
                        preserve_repository_root=preserve_repository_root,
                    )
                ).sha
            except FileNotFoundError:
                sha = None
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if len(raw) > _MAX_FILE_BYTES:
            raise ProjectProviderError("Fayl hajmi ruxsat etilgan chegaradan katta.")
        session, settings = await self._session()
        try:
            payload: dict[str, str] = {
                "message": message,
                "content": base64.b64encode(raw).decode("ascii"),
                "branch": settings["branch"],
            }
            if sha:
                payload["sha"] = sha
            status, body = await self._request(
                session,
                "PUT",
                self._url(settings, f"contents/{normalized}"),
                json=payload,
            )
        finally:
            await session.close()
        if status not in (200, 201):
            raise ProjectProviderError(f"GitHub yozish HTTP {status}: {body[:500]}")
        await self.clear_cache()
        return json.loads(body)

    async def delete_file(
        self,
        path: str,
        message: str,
        *,
        sha: str | None = None,
        preserve_repository_root: bool = False,
    ) -> dict:
        normalized = self._safe_path(
            path,
            preserve_repository_root=preserve_repository_root,
        )
        if sha is None:
            sha = (
                await self.get_file(
                    normalized,
                    force=True,
                    preserve_repository_root=preserve_repository_root,
                )
            ).sha
        session, settings = await self._session()
        try:
            status, body = await self._request(
                session,
                "DELETE",
                self._url(settings, f"contents/{normalized}"),
                json={"message": message, "sha": sha, "branch": settings["branch"]},
            )
        finally:
            await session.close()
        if status != 200:
            raise ProjectProviderError(f"GitHub o'chirish HTTP {status}: {body[:500]}")
        await self.clear_cache()
        return json.loads(body)

    async def rename_file(self, old_path: str, new_path: str, message: str) -> None:
        old = await self.get_file(old_path, force=True)
        await self.put_file(new_path, old.content, message)
        await self.delete_file(old.path, message, sha=old.sha)

    async def search_name(self, query: str, limit: int = 40) -> list[str]:
        q = query.casefold()
        entries = await self.tree()
        return [e.path for e in entries if e.kind == "file" and q in e.path.casefold()][:limit]

    async def search_text(
        self,
        query: str,
        *,
        extensions: set[str] | None = None,
        limit: int = 30,
    ) -> list[tuple[str, int, str]]:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results: list[tuple[str, int, str]] = []
        for entry in await self.tree():
            if entry.kind != "file":
                continue
            if extensions and posixpath.splitext(entry.path)[1].lower() not in extensions:
                continue
            try:
                file = await self.get_file(entry.path)
            except (FileNotFoundError, ProjectProviderError):
                continue
            for line_number, line in enumerate(file.content.splitlines(), 1):
                if pattern.search(line):
                    results.append((entry.path, line_number, line.strip()))
                    if len(results) >= min(limit, _MAX_SEARCH_HITS):
                        return results
        return results

    async def find_identifier(self, name: str, limit: int = 30) -> list[tuple[str, int, str]]:
        escaped = re.escape(name.strip())
        patterns = [
            re.compile(rf"\b(?:async\s+)?def\s+{escaped}\b"),
            re.compile(rf"\bclass\s+{escaped}\b"),
            re.compile(rf"\b(?:const|let|var|function)\s+{escaped}\b"),
            re.compile(rf"^{escaped}\s*="),
        ]
        results: list[tuple[str, int, str]] = []
        for entry in await self.tree():
            if entry.kind != "file":
                continue
            try:
                file = await self.get_file(entry.path)
            except (FileNotFoundError, ProjectProviderError):
                continue
            for line_number, line in enumerate(file.content.splitlines(), 1):
                if any(pattern.search(line) for pattern in patterns):
                    results.append((entry.path, line_number, line.strip()))
                    if len(results) >= min(limit, _MAX_SEARCH_HITS):
                        return results
        return results

    async def export_zip(self) -> bytes:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for entry in await self.tree():
                if entry.kind != "file":
                    continue
                try:
                    raw, _ = await self.get_file_bytes(entry.path)
                except (FileNotFoundError, ProjectProviderError):
                    continue
                output.writestr(entry.path, raw)
        return archive.getvalue()


_provider = GitHubProjectProvider()


def get_project_provider() -> GitHubProjectProvider:
    return _provider