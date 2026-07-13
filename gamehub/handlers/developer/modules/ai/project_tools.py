"""AI Developer Phase 4 — Project Tools.

Features
────────
🔎 Loyihani skanerlash — AI analyses the full project for issues
📋 Fayllar xaritasi   — generate a file tree of gamehub/
🧪 To'liq test        — syntax-check all .py files with py_compile
📦 Backup yaratish    — zip the entire gamehub/ directory (preview → confirm)

Scan, map and test are read-only; they execute immediately.
Backup requires explicit confirmation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import py_compile
import zipfile
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL, AI_MENU,
    AI_PROJ_SCAN, AI_PROJ_MAP, AI_PROJ_TEST, AI_PROJ_BACKUP,
    AI_PROJ_OK,
)
from handlers.developer.modules.ai import services
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:project_tools")

_BASE    = Path(__file__).resolve().parents[4]   # gamehub/
_TG_MAX  = 4096

# Directories/patterns to skip in scan and map
_SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", "venv", ".venv",
    "clones", "backups", "logs",
}
_SKIP_EXT = {".pyc", ".pyo", ".log", ".zip"}


# ── FSM States ────────────────────────────────────────────────────────────────

class ProjStates(StatesGroup):
    confirming = State()   # only backup needs confirm


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID

async def _guard_cb(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash", callback_data=AI_PROJ_OK),
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


# ── File tree ─────────────────────────────────────────────────────────────────

def _build_tree(root: Path, prefix: str = "", max_depth: int = 5, depth: int = 0) -> list[str]:
    if depth > max_depth:
        return [f"{prefix}..."]
    lines: list[str] = []
    try:
        items = sorted(
            [p for p in root.iterdir()
             if p.name not in _SKIP_DIRS and p.suffix not in _SKIP_EXT],
            key=lambda p: (p.is_file(), p.name),
        )
    except PermissionError:
        return [f"{prefix}[permission denied]"]

    for i, item in enumerate(items):
        is_last   = i == len(items) - 1
        connector = "    " if is_last else "│   "
        branch    = "└── " if is_last else "├── "
        if item.is_dir():
            lines.append(f"{prefix}{branch}{item.name}/")
            lines.extend(_build_tree(item, prefix + connector, max_depth, depth + 1))
        else:
            size = item.stat().st_size
            lines.append(f"{prefix}{branch}{item.name}  ({size:,} B)")
    return lines


# ── Syntax check ──────────────────────────────────────────────────────────────

def _check_syntax(root: Path) -> tuple[int, int, list[str]]:
    """Return (ok_count, err_count, errors)."""
    ok_count  = 0
    err_count = 0
    errors: list[str] = []
    for py in root.rglob("*.py"):
        if any(skip in py.parts for skip in _SKIP_DIRS):
            continue
        try:
            py_compile.compile(str(py), doraise=True)
            ok_count += 1
        except py_compile.PyCompileError as exc:
            err_count += 1
            errors.append(str(exc))
    return ok_count, err_count, errors


# ── Zip backup ────────────────────────────────────────────────────────────────

def _create_zip(root: Path, dest: Path) -> int:
    """Zip root into dest. Returns number of files added."""
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root.parent)
                if any(skip in rel.parts for skip in _SKIP_DIRS):
                    continue
                if path.suffix in _SKIP_EXT:
                    continue
                zf.write(path, rel)
                count += 1
    return count


# ── AI scan prompt ────────────────────────────────────────────────────────────

def _build_scan_context(root: Path, max_chars: int = 6000) -> str:
    """Collect key Python files to feed into AI for analysis."""
    snippets: list[str] = []
    total    = 0
    priority = ["main.py", "config.py", "bot/router.py"]

    def add(path: Path) -> None:
        nonlocal total
        if total >= max_chars:
            return
        try:
            text = path.read_text("utf-8", errors="replace")[:2000]
            rel  = str(path.relative_to(root))
            snippets.append(f"### {rel}\n```python\n{text}\n```")
            total += len(text)
        except Exception:
            pass

    for name in priority:
        p = root / name
        if p.exists():
            add(p)

    for py in sorted(root.rglob("*.py")):
        if total >= max_chars:
            break
        if any(skip in py.parts for skip in _SKIP_DIRS):
            continue
        add(py)

    return "\n\n".join(snippets)


# ════════════════════════════════════════════════════════════════════════════
# 🔎 Loyihani skanerlash
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_PROJ_SCAN)
async def cb_proj_scan(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text(
        "Loyiha skanerlanyapti... Bu 30-60 soniya olishi mumkin.",
        parse_mode="HTML",
    )

    context = await asyncio.to_thread(_build_scan_context, _BASE)
    prompt  = (
        "Quyidagi Python/HTML5 loyiha kodini professional audit qil:\n\n"
        f"{context}\n\n"
        "Hisobotni quyidagi bo'limlarda yoz (o'zbek tilida):\n"
        "1. Kritik xatolar\n"
        "2. Takroriy kodlar (DRY buzilishi)\n"
        "3. Ishlatilmayotgan funksiya/modul (agar ko'rsak)\n"
        "4. Xavfsizlik muammolari\n"
        "5. Optimizatsiya tavsiyalari\n"
        "6. Umumiy baho (100 ball)\n\n"
        "Har bir muammo uchun: qaysi fayl, nima muammo, qanday tuzatish."
    )

    result = await services.get_manager().generate_text(prompt)

    if result.ok:
        text = f"<b>Loyiha auditi</b>\n\n{result.content}"
    else:
        text = f"<b>AI xatosi</b>\n\n<code>{result.error}</code>"

    chunks = [text[i: i + _TG_MAX] for i in range(0, max(len(text), 1), _TG_MAX)]
    for i, chunk in enumerate(chunks):
        kb = _back_kb() if i == len(chunks) - 1 else None
        await q.message.answer(chunk, reply_markup=kb, parse_mode="HTML")

    await log_action(q.from_user.id, "PROJ_SCAN", "full project", "ok" if result.ok else "ai_error")


# ════════════════════════════════════════════════════════════════════════════
# 📋 Fayllar xaritasi
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_PROJ_MAP)
async def cb_proj_map(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()

    tree_lines = await asyncio.to_thread(_build_tree, _BASE)
    tree_text  = "\n".join(tree_lines)
    total_py   = sum(1 for _ in _BASE.rglob("*.py"))
    total_html = sum(1 for _ in _BASE.rglob("*.html"))

    header = (
        f"<b>Fayllar xaritasi — gamehub/</b>\n"
        f"Python: {total_py} | HTML: {total_html}\n\n"
        "<pre>"
    )
    footer = "</pre>"

    full = header + tree_text[:3200] + footer
    await q.message.edit_text(full, reply_markup=_back_kb(), parse_mode="HTML")
    await log_action(q.from_user.id, "PROJ_MAP", "gamehub/", "ok")


# ════════════════════════════════════════════════════════════════════════════
# 🧪 To'liq test
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_PROJ_TEST)
async def cb_proj_test(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("Python sintaksis tekshiruvi bajarilmoqda...")

    ok_n, err_n, errors = await asyncio.to_thread(_check_syntax, _BASE)

    if err_n == 0:
        text = (
            f"<b>To'liq test — MUVAFFAQIYATLI</b>\n\n"
            f"Tekshirildi: {ok_n + err_n} fayl\n"
            f"Xatolar: 0\n\n"
            f"Barcha Python fayllar sintaksis jihatidan to'g'ri."
        )
    else:
        err_list = "\n".join(f"• {e[:200]}" for e in errors[:20])
        if len(errors) > 20:
            err_list += f"\n... +{len(errors) - 20} xato"
        text = (
            f"<b>To'liq test — XATOLAR TOPILDI</b>\n\n"
            f"Tekshirildi: {ok_n + err_n} fayl\n"
            f"Muvaffaqiyatli: {ok_n}\n"
            f"Xatoli: {err_n}\n\n"
            f"<pre>{err_list[:2000]}</pre>"
        )

    await q.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await log_action(q.from_user.id, "PROJ_TEST", f"{ok_n+err_n} files",
                     f"ok={ok_n} err={err_n}")


# ════════════════════════════════════════════════════════════════════════════
# 📦 Backup yaratish
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_PROJ_BACKUP)
async def cb_proj_backup_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.update_data(operation="backup")
    await state.set_state(ProjStates.confirming)
    await q.answer()

    backup_dir  = _BASE / "backups"
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name    = f"gamehub_backup_{ts}.zip"
    dest        = backup_dir / zip_name

    # Count files to be backed up
    file_count  = sum(
        1 for p in _BASE.rglob("*")
        if p.is_file()
        and not any(skip in p.parts for skip in _SKIP_DIRS)
        and p.suffix not in _SKIP_EXT
    )

    await state.update_data(dest=str(dest), zip_name=zip_name)
    await q.message.edit_text(
        f"<b>Backup yaratish — preview</b>\n\n"
        f"Papka: <code>gamehub/</code>\n"
        f"Fayllar: {file_count}\n"
        f"Backup nomi: <code>{zip_name}</code>\n"
        f"Saqlash joyi: <code>backups/</code>\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(), parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == AI_PROJ_OK,
    StateFilter(ProjStates.confirming),
)
async def cb_proj_backup_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data     = await state.get_data()
    dest     = Path(data["dest"])
    zip_name = data["zip_name"]
    await state.clear()
    await q.answer()
    await q.message.edit_text("Backup yaratilmoqda...")

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        count = await asyncio.to_thread(_create_zip, _BASE, dest)
        size  = dest.stat().st_size
        size_mb = size / 1_048_576
        await q.message.edit_text(
            f"<b>Backup tayyor</b>\n\n"
            f"Fayl: <code>{zip_name}</code>\n"
            f"Hajm: {size_mb:.2f} MB\n"
            f"Fayllar: {count}",
            reply_markup=_back_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PROJ_BACKUP", zip_name, f"{size_mb:.2f}MB/{count}files")
    except Exception as exc:
        await q.message.edit_text(
            f"Backup xatosi: <code>{exc}</code>",
            reply_markup=_back_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PROJ_BACKUP", zip_name, f"error:{exc}")
