"""AI Developer — Project-aware file search service.

Provides reusable, async-safe helpers for exploring the gamehub/ project.
No Telegram dependency — pure data layer usable from any handler.

Public API
──────────
    await list_files(folder_hint)     → list all files inside a folder
    await open_file(path_hint)        → read a file by path or filename
    await find_identifier(name)       → find def/class/var declarations
    await search_text(query)          → grep-style search across the repo
    await project_structure()         → full indented file tree

All functions return ProjectResult(found: bool, text: str) where
``text`` is HTML-formatted and ready for Telegram (already HTML-escaped).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

# gamehub/ — same anchor used by action_log.py and project_tools.py
_BASE = Path(__file__).resolve().parents[4]

_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", "node_modules", "venv", ".venv",
    "clones", "backups", "logs",
})
_SKIP_EXT: frozenset[str] = frozenset({".pyc", ".pyo", ".log", ".zip"})

# Chars shown when displaying a file (keeps result in ≈1 Telegram message)
_MAX_FILE_CHARS = 3_000
# Maximum search hits returned
_MAX_HITS = 30


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ProjectResult:
    found: bool
    text: str   # HTML-formatted, safe for parse_mode="HTML"


# ── HTML escaping ─────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Sync helpers (run inside asyncio.to_thread) ───────────────────────────────

def _all_files(root: Path) -> list[Path]:
    """Walk root recursively, skipping ignored dirs/extensions."""
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(skip in p.parts for skip in _SKIP_DIRS):
            continue
        if p.suffix in _SKIP_EXT:
            continue
        out.append(p)
    return out


def _build_tree(root: Path) -> str:
    """Indented file tree string."""
    lines = [f"gamehub/"]
    for p in sorted(root.rglob("*")):
        if any(skip in p.parts for skip in _SKIP_DIRS):
            continue
        if p.suffix in _SKIP_EXT:
            continue
        rel   = p.relative_to(root)
        depth = len(rel.parts) - 1
        pad   = "  " * depth
        icon  = "📁 " if p.is_dir() else "📄 "
        lines.append(f"{pad}{icon}{p.name}")
    return "\n".join(lines)


def _resolve_path(hint: str) -> Path | None:
    """Find a file from a full, partial, or bare filename hint."""
    # 1. Direct from _BASE
    c = _BASE / hint
    if c.is_file():
        return c
    # 2. Strip leading "gamehub/" prefix
    stripped = re.sub(r"^gamehub[/\\]", "", hint)
    c = _BASE / stripped
    if c.is_file():
        return c
    # 3. Bare filename search (first match wins)
    name = Path(hint).name
    for p in sorted(_BASE.rglob(name)):
        if p.is_file() and not any(sk in p.parts for sk in _SKIP_DIRS):
            return p
    return None


def _grep(query: str, root: Path) -> list[tuple[Path, int, str]]:
    """Grep-style search; returns up to _MAX_HITS (path, lineno, stripped_line)."""
    hits: list[tuple[Path, int, str]] = []
    pat = re.compile(re.escape(query), re.IGNORECASE)
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(sk in p.parts for sk in _SKIP_DIRS):
            continue
        if p.suffix in _SKIP_EXT:
            continue
        try:
            for i, line in enumerate(
                p.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pat.search(line):
                    hits.append((p, i, line.strip()))
                    if len(hits) >= _MAX_HITS:
                        return hits
        except OSError:
            continue
    return hits


def _find_ident(name: str, root: Path) -> list[tuple[Path, int, str]]:
    """Find function/class/variable declarations."""
    hits: list[tuple[Path, int, str]] = []
    pats = [
        re.compile(rf"\bdef\s+{re.escape(name)}\b"),
        re.compile(rf"\basync\s+def\s+{re.escape(name)}\b"),
        re.compile(rf"\bclass\s+{re.escape(name)}\b"),
        re.compile(rf"\b(?:const|let|var|function)\s+{re.escape(name)}\b"),
        re.compile(rf"^{re.escape(name)}\s*=", re.MULTILINE),
    ]
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(sk in p.parts for sk in _SKIP_DIRS):
            continue
        if p.suffix in _SKIP_EXT:
            continue
        try:
            for i, line in enumerate(
                p.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if any(pat.search(line) for pat in pats):
                    hits.append((p, i, line.strip()))
                    if len(hits) >= _MAX_HITS:
                        return hits
        except OSError:
            continue
    return hits


def _find_folder(hint: str) -> Path | None:
    """Resolve a folder hint to a Path under _BASE."""
    # Direct
    c = _BASE / hint
    if c.is_dir():
        return c
    # Strip leading gamehub/
    stripped = re.sub(r"^gamehub[/\\]", "", hint)
    c = _BASE / stripped
    if c.is_dir():
        return c
    # Search by directory name
    for p in sorted(_BASE.rglob(hint)):
        if p.is_dir() and not any(sk in p.parts for sk in _SKIP_DIRS):
            return p
    return None


# ── Public async API ──────────────────────────────────────────────────────────

async def list_files(folder_hint: str) -> ProjectResult:
    """List all non-ignored files inside a folder."""
    folder = await asyncio.to_thread(_find_folder, folder_hint.strip())
    if folder is None:
        return ProjectResult(
            found=False,
            text=f"❌ <b>Papka topilmadi:</b> <code>{_esc(folder_hint)}</code>",
        )
    files = await asyncio.to_thread(_all_files, folder)
    rel   = folder.relative_to(_BASE)
    if not files:
        return ProjectResult(
            found=True,
            text=f"📁 <b>{_esc(str(rel))}/</b> — fayl topilmadi.",
        )
    lines = [f"📁 <b>{_esc(str(rel))}/</b> — {len(files)} ta fayl\n"]
    for p in files:
        lines.append(f"  📄 <code>{_esc(str(p.relative_to(_BASE)))}</code>")
    return ProjectResult(found=True, text="\n".join(lines))


async def open_file(path_hint: str) -> ProjectResult:
    """Open and show file contents (truncated to fit a Telegram message)."""
    path = await asyncio.to_thread(_resolve_path, path_hint.strip())
    if path is None:
        return ProjectResult(
            found=False,
            text=f"❌ <b>Fayl topilmadi:</b> <code>{_esc(path_hint)}</code>",
        )
    try:
        raw = await asyncio.to_thread(
            path.read_text, encoding="utf-8", errors="replace"
        )
    except OSError as exc:
        return ProjectResult(
            found=False,
            text=f"❌ <b>O'qishda xato:</b> <code>{_esc(str(exc))}</code>",
        )

    rel       = path.relative_to(_BASE)
    total     = len(raw)
    truncated = total > _MAX_FILE_CHARS
    display   = raw[:_MAX_FILE_CHARS]

    header = f"📄 <b>{_esc(str(rel))}</b>  ({total} belgi, {raw.count(chr(10))+1} qator)"
    if truncated:
        header += f"\n<i>⚠️ Birinchi {_MAX_FILE_CHARS} belgi ko'rsatilmoqda</i>"
    body = f"<pre>{_esc(display)}</pre>"
    return ProjectResult(found=True, text=f"{header}\n\n{body}")


async def find_identifier(name: str) -> ProjectResult:
    """Find function / class / variable declarations by name."""
    hits = await asyncio.to_thread(_find_ident, name.strip(), _BASE)
    if not hits:
        return ProjectResult(
            found=False,
            text=f"❌ <b>Topilmadi:</b> <code>{_esc(name)}</code>",
        )
    lines = [f"🔍 <b>{_esc(name)}</b> — {len(hits)} ta natija:\n"]
    for path, lineno, line in hits:
        rel = path.relative_to(_BASE)
        lines.append(f"📄 <code>{_esc(str(rel))}:{lineno}</code>")
        lines.append(f"  <code>{_esc(line[:120])}</code>\n")
    return ProjectResult(found=True, text="\n".join(lines))


async def search_text(query: str) -> ProjectResult:
    """Grep-style full-text search across the whole project."""
    hits = await asyncio.to_thread(_grep, query.strip(), _BASE)
    if not hits:
        return ProjectResult(
            found=False,
            text=f"❌ <b>Matn topilmadi:</b> <code>{_esc(query)}</code>",
        )
    lines = [f"🔎 <b>{_esc(query)}</b> — {len(hits)} ta natija:\n"]
    for path, lineno, line in hits:
        rel = path.relative_to(_BASE)
        lines.append(f"📄 <code>{_esc(str(rel))}:{lineno}</code>")
        lines.append(f"  <code>{_esc(line[:120])}</code>\n")
    return ProjectResult(found=True, text="\n".join(lines))


async def project_structure() -> ProjectResult:
    """Return the full indented file tree of gamehub/."""
    tree = await asyncio.to_thread(_build_tree, _BASE)
    return ProjectResult(
        found=True,
        text=(
            "🗂 <b>Loyiha tuzilmasi</b> (<code>gamehub/</code>)\n\n"
            f"<pre>{_esc(tree)}</pre>"
        ),
    )
