"""GitHub-backed project search used by AI Chat.

The public API intentionally remains unchanged so the Telegram command parser
and its FSM do not need to know where the project is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from services.project_provider import ProjectProviderError, get_project_provider

_MAX_FILE_CHARS = 3_000
_MAX_HITS = 30


@dataclass
class ProjectResult:
    found: bool
    text: str


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _display_path(path: str) -> str:
    return path.removeprefix("gamehub/")


def _resolve(path_hint: str) -> str:
    """Map a user-typed path hint (with or without a leading ``gamehub/``)
    to the real repository path under ``gamehub/`` — the tree that's
    actually deployed and served (see file_tools.py's own ``_resolve`` for
    the identical convention). Without this, a hint like
    "webapp/games/x.html" would resolve to the unused repository-root
    ``webapp/`` tree instead of the live ``gamehub/webapp/`` one.
    """
    provider = get_project_provider()
    try:
        rel = provider.normalize_path(path_hint)
    except ProjectProviderError:
        return "gamehub"
    return rel if (rel == "gamehub" or rel.startswith("gamehub/")) else f"gamehub/{rel}"


async def _failure(exc: Exception) -> ProjectResult:
    return ProjectResult(False, f"❌ <b>GitHub loyiha xatosi:</b> <code>{_esc(str(exc))}</code>")


async def list_files(folder_hint: str) -> ProjectResult:
    try:
        provider = get_project_provider()
        folder = _resolve(folder_hint) if folder_hint.strip() else ""
        entries = await provider.list_files(folder, preserve_repository_root=True)
        files = [entry for entry in entries if entry.kind == "file"]
        label = folder.strip("/") or "repository"
        if not files:
            return ProjectResult(True, f"📁 <b>{_esc(label)}/</b> — fayl topilmadi.")
        lines = [f"📁 <b>{_esc(label)}/</b> — {len(files)} ta fayl\n"]
        lines.extend(f"  📄 <code>{_esc(_display_path(e.path))}</code>" for e in files)
        return ProjectResult(True, "\n".join(lines))
    except Exception as exc:
        return await _failure(exc)


async def open_file(path_hint: str) -> ProjectResult:
    try:
        provider = get_project_provider()
        path = _resolve(path_hint.strip())
        try:
            file = await provider.get_file(path, preserve_repository_root=True)
        except FileNotFoundError:
            matches = await provider.search_name(PurePosixPath(path_hint).name, limit=5)
            if len(matches) != 1:
                return ProjectResult(
                    False,
                    f"❌ <b>Fayl topilmadi:</b> <code>{_esc(path_hint)}</code>",
                )
            # matches[0] already comes back as a real repo path from
            # tree() — pass it through as-is (preserve_repository_root=True)
            # instead of stripping a "gamehub/" prefix it may carry.
            file = await provider.get_file(matches[0], preserve_repository_root=True)
        raw = file.content
        display = raw[:_MAX_FILE_CHARS]
        header = (
            f"📄 <b>{_esc(_display_path(file.path))}</b>  "
            f"({len(raw)} belgi, {raw.count(chr(10)) + 1} qator)"
        )
        if len(raw) > _MAX_FILE_CHARS:
            header += f"\n<i>⚠️ Birinchi {_MAX_FILE_CHARS} belgi ko'rsatilmoqda</i>"
        return ProjectResult(True, f"{header}\n\n<pre>{_esc(display)}</pre>")
    except Exception as exc:
        return await _failure(exc)


async def find_identifier(name: str) -> ProjectResult:
    try:
        hits = await get_project_provider().find_identifier(name.strip(), _MAX_HITS)
        if not hits:
            return ProjectResult(False, f"❌ <b>Topilmadi:</b> <code>{_esc(name)}</code>")
        lines = [f"🔍 <b>{_esc(name)}</b> — {len(hits)} ta natija:\n"]
        for path, line_number, line in hits:
            lines.append(f"📄 <code>{_esc(_display_path(path))}:{line_number}</code>")
            lines.append(f"  <code>{_esc(line[:120])}</code>\n")
        return ProjectResult(True, "\n".join(lines))
    except Exception as exc:
        return await _failure(exc)


async def search_text(query: str) -> ProjectResult:
    try:
        hits = await get_project_provider().search_text(query.strip(), limit=_MAX_HITS)
        if not hits:
            return ProjectResult(False, f"❌ <b>Matn topilmadi:</b> <code>{_esc(query)}</code>")
        lines = [f"🔎 <b>{_esc(query)}</b> — {len(hits)} ta natija:\n"]
        for path, line_number, line in hits:
            lines.append(f"📄 <code>{_esc(_display_path(path))}:{line_number}</code>")
            lines.append(f"  <code>{_esc(line[:120])}</code>\n")
        return ProjectResult(True, "\n".join(lines))
    except Exception as exc:
        return await _failure(exc)


async def project_structure() -> ProjectResult:
    try:
        entries = await get_project_provider().tree()
        lines = ["repository/"]
        for entry in entries:
            parts = entry.path.split("/")
            depth = len(parts) - 1
            icon = "📁 " if entry.kind == "dir" else "📄 "
            lines.append(f"{'  ' * depth}{icon}{parts[-1]}")
        return ProjectResult(
            True,
            "🗂 <b>Loyiha tuzilmasi</b> (GitHub repository)\n\n"
            f"<pre>{_esc(chr(10).join(lines))}</pre>",
        )
    except Exception as exc:
        return await _failure(exc)