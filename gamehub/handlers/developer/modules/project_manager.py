"""Developer Mode › 📦 Project Manager

Features
────────
📂 Project Information  — name, path, file/folder counts, size, Python, git branch, uptime
📊 Project Statistics   — file counts broken down by type
🔍 Search               — by filename or by text content inside files
🧹 Maintenance          — clear __pycache__, remove temp files, show disk usage
📦 Export               — create ZIP archive and deliver as Telegram document

Safety rules
────────────
• Destructive maintenance actions (pycache clear, temp removal) require confirmation.
• Every mutating action is logged via action_log.
• ZIP export is streamed from disk via FSInputFile — no RAM buffering.
• Search results are capped to avoid hitting Telegram message limits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from handlers.developer.callbacks import (
    DEV_PROJECT_MANAGER,
    DEV_PM_INFO, DEV_PM_STATS,
    DEV_PM_SEARCH, DEV_PM_SRCH_NAME, DEV_PM_SRCH_TEXT,
    DEV_PM_MAINT, DEV_PM_PYCACHE, DEV_PM_PYCACHE_OK,
    DEV_PM_TEMP, DEV_PM_TEMP_OK, DEV_PM_DISK,
    DEV_PM_EXPORT, DEV_PM_EXPORT_OK,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:project_manager")

# gamehub/ root — parents[3] from modules/project_manager.py
_BASE       = Path(__file__).resolve().parents[3]
_BACKUP_DIR = _BASE / "backups"
_TG_MAX     = 4096

_SKIP_DIRS = {"__pycache__", ".git", "node_modules", "venv", ".venv", "clones"}
_SKIP_EXT  = {".pyc", ".pyo"}

# Text-searchable extensions
_TEXT_EXTS = {".py", ".html", ".js", ".css", ".json", ".md", ".txt", ".yaml", ".yml", ".toml"}


# ── FSM States ────────────────────────────────────────────────────────────────

class PMSearchStates(StatesGroup):
    waiting_name  = State()
    waiting_text  = State()

class PMConfirmStates(StatesGroup):
    confirm_pycache = State()
    confirm_temp    = State()
    confirm_export  = State()


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID

async def _guard_cb(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False

async def _guard_msg(m: Message) -> bool:
    if _is_admin(m.from_user.id):
        return True
    await m.answer("⛔ Ruxsat yo'q.")
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📂 Ma'lumot",      callback_data=DEV_PM_INFO),
            InlineKeyboardButton(text="📊 Statistika",    callback_data=DEV_PM_STATS),
        ],
        [
            InlineKeyboardButton(text="🔍 Qidirish",      callback_data=DEV_PM_SEARCH),
            InlineKeyboardButton(text="🧹 Xizmat",        callback_data=DEV_PM_MAINT),
        ],
        [
            InlineKeyboardButton(text="📦 Eksport (ZIP)", callback_data=DEV_PM_EXPORT),
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga",        callback_data="dev:menu"),
        ],
    ])

def _search_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 Fayl nomi bo'yicha", callback_data=DEV_PM_SRCH_NAME),
            InlineKeyboardButton(text="📝 Matn bo'yicha",      callback_data=DEV_PM_SRCH_TEXT),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER)],
    ])

def _maint_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 __pycache__ tozalash", callback_data=DEV_PM_PYCACHE),
            InlineKeyboardButton(text="🧹 Vaqtinchalik fayllar", callback_data=DEV_PM_TEMP),
        ],
        [
            InlineKeyboardButton(text="💾 Disk foydalanish",     callback_data=DEV_PM_DISK),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER)],
    ])

def _confirm_kb(ok_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=ok_cb),
        InlineKeyboardButton(text="❌ Bekor",      callback_data=DEV_PROJECT_MANAGER),
    ]])

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=DEV_PROJECT_MANAGER),
    ]])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _get_process_start() -> str:
    try:
        pid = os.getpid()
        stat_text = Path(f"/proc/{pid}/stat").read_text()
        after_paren = stat_text.split(")", 1)[1].strip()
        fields = after_paren.split()
        start_ticks = int(fields[19])
        clk_tck = os.sysconf("SC_CLK_TCK")
        uptime_s = float(Path("/proc/uptime").read_text().split()[0])
        boot_epoch = time.time() - uptime_s
        start_epoch = boot_epoch + start_ticks / clk_tck
        return datetime.fromtimestamp(start_epoch).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "(aniqlanmadi)"


async def _git_branch() -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "branch", "--show-current",
            cwd=str(_BASE),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        branch = out.decode().strip()
        return branch or "unknown"
    except Exception:
        return "unknown"


def _walk(root: Path, skip_dirs: set[str] = _SKIP_DIRS):
    """Yield all files under root, skipping known noise dirs."""
    for item in root.rglob("*"):
        if any(part in skip_dirs for part in item.parts):
            continue
        yield item


def _count_and_size(root: Path) -> tuple[int, int, int]:
    """Return (file_count, dir_count, total_bytes)."""
    files = dirs = 0
    total = 0
    for item in _walk(root):
        if item.is_file():
            files += 1
            total += item.stat().st_size
        elif item.is_dir():
            dirs += 1
    return files, dirs, total


def _stats_by_type(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {
        "Python (.py)":      0,
        "HTML (.html)":      0,
        "CSS (.css)":        0,
        "JavaScript (.js)":  0,
        "Rasmlar":           0,
        "Ma'lumotlar bazasi": 0,
        "Boshqa":            0,
    }
    _img_exts  = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"}
    _db_exts   = {".db", ".sqlite", ".sqlite3"}
    for item in _walk(root):
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if ext == ".py":
            counts["Python (.py)"] += 1
        elif ext == ".html":
            counts["HTML (.html)"] += 1
        elif ext == ".css":
            counts["CSS (.css)"] += 1
        elif ext == ".js":
            counts["JavaScript (.js)"] += 1
        elif ext in _img_exts:
            counts["Rasmlar"] += 1
        elif ext in _db_exts:
            counts["Ma'lumotlar bazasi"] += 1
        else:
            counts["Boshqa"] += 1
    return counts


def _search_by_name(root: Path, query: str, limit: int = 40) -> list[str]:
    q = query.lower()
    results: list[str] = []
    for item in _walk(root):
        if item.is_file() and q in item.name.lower():
            results.append(str(item.relative_to(root)))
            if len(results) >= limit:
                break
    return results


def _search_in_files(root: Path, query: str, limit: int = 20) -> list[tuple[str, int, str]]:
    """Return list of (rel_path, line_num, line_text)."""
    q_lower = query.lower()
    results: list[tuple[str, int, str]] = []
    for item in _walk(root):
        if not item.is_file():
            continue
        if item.suffix.lower() not in _TEXT_EXTS:
            continue
        try:
            lines = item.read_text("utf-8", errors="replace").splitlines()
            for lineno, line in enumerate(lines, 1):
                if q_lower in line.lower():
                    rel = str(item.relative_to(root))
                    results.append((rel, lineno, line.strip()[:120]))
                    if len(results) >= limit:
                        return results
        except Exception:
            continue
    return results


def _find_pycache(root: Path) -> list[Path]:
    return [p for p in root.rglob("__pycache__") if p.is_dir()]


def _find_temp_files(root: Path) -> list[Path]:
    """Find .pyc / .pyo files outside __pycache__, plus old ZIPs in backups/."""
    found: list[Path] = []
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        if item.suffix in {".pyc", ".pyo"}:
            found.append(item)
        elif item.suffix == ".zip" and _BACKUP_DIR in item.parents:
            found.append(item)
    return found


def _create_zip(root: Path, dest: Path) -> int:
    """Zip root into dest. Returns file count."""
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(skip in path.parts for skip in _SKIP_DIRS | {"backups", "logs"}):
                continue
            if path.suffix in _SKIP_EXT:
                continue
            rel = path.relative_to(root.parent)
            zf.write(path, rel)
            count += 1
    return count


def _disk_usage(root: Path) -> list[tuple[str, int]]:
    """Size of each top-level subdirectory (and root files) in gamehub/."""
    entries: list[tuple[str, int]] = []
    for item in sorted(root.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            entries.append((f"📁 {item.name}/", size))
        else:
            entries.append((f"📄 {item.name}", item.stat().st_size))
    entries.sort(key=lambda x: x[1], reverse=True)
    return entries


# ── Entry point — main Project Manager menu ───────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_PROJECT_MANAGER)
async def cb_pm_main(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "📦 <b>Project Manager</b>\n\n"
        "Loyihani boshqarish va tahlil qilish.\n\n"
        "• Ma'lumot — umumiy loyiha statistikasi\n"
        "• Statistika — fayllar turi bo'yicha\n"
        "• Qidirish — fayl nomi yoki matn bo'yicha\n"
        "• Xizmat — tozalash va disk foydalanishi\n"
        "• Eksport — ZIP arxiv yaratish",
        reply_markup=_main_kb(),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════════════════════════
# 📂 Project Information
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_PM_INFO)
async def cb_pm_info(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("⏳ Ma'lumotlar yig'ilmoqda...", parse_mode="HTML")

    file_cnt, dir_cnt, total_bytes = await asyncio.to_thread(_count_and_size, _BASE)
    branch   = await _git_branch()
    py_ver   = sys.version.split()[0]
    restart  = await asyncio.to_thread(_get_process_start)

    text = (
        "📂 <b>Loyiha ma'lumoti</b>\n\n"
        f"<b>Nomi:</b>           <code>{_BASE.name}</code>\n"
        f"<b>Yo'l:</b>           <code>{_BASE}</code>\n"
        f"<b>Jami fayllar:</b>   {file_cnt:,}\n"
        f"<b>Jami papkalar:</b>  {dir_cnt:,}\n"
        f"<b>Umumiy hajm:</b>    {_fmt_size(total_bytes)}\n"
        f"<b>Python:</b>         {py_ver}\n"
        f"<b>Git branch:</b>     <code>{branch}</code>\n"
        f"<b>So'nggi restart:</b> {restart}"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER),
    ]])
    await q.message.edit_text(text, reply_markup=back_kb, parse_mode="HTML")
    await log_action(q.from_user.id, "PM_INFO", str(_BASE), "ok")


# ════════════════════════════════════════════════════════════════════════════
# 📊 Project Statistics
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_PM_STATS)
async def cb_pm_stats(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("⏳ Hisoblanmoqda...", parse_mode="HTML")

    counts = await asyncio.to_thread(_stats_by_type, _BASE)
    total  = sum(counts.values())

    lines = ["📊 <b>Fayl statistikasi</b>\n"]
    for label, cnt in counts.items():
        bar_len  = int(cnt / max(total, 1) * 20)
        bar      = "█" * bar_len + "░" * (20 - bar_len)
        pct      = cnt / max(total, 1) * 100
        lines.append(f"<b>{label}</b>\n{bar}  {cnt:,} ({pct:.1f}%)\n")
    lines.append(f"\n<b>Jami:</b> {total:,} fayl")

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER),
    ]])
    await q.message.edit_text("\n".join(lines), reply_markup=back_kb, parse_mode="HTML")
    await log_action(q.from_user.id, "PM_STATS", str(_BASE), f"total={total}")


# ════════════════════════════════════════════════════════════════════════════
# 🔍 Search — sub-menu
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_PM_SEARCH)
async def cb_pm_search_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🔍 <b>Qidirish</b>\n\n"
        "• <b>Fayl nomi</b> — fayl nomidagi so'z bo'yicha (max 40 natija)\n"
        "• <b>Matn</b> — fayllar ichidagi matn bo'yicha (max 20 natija)",
        reply_markup=_search_kb(),
        parse_mode="HTML",
    )


# ── Search by filename ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_PM_SRCH_NAME)
async def cb_pm_srch_name_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(PMSearchStates.waiting_name)
    await q.answer()
    await q.message.edit_text(
        "📄 <b>Fayl nomi bo'yicha qidirish</b>\n\n"
        "Qidiruv so'zini yozing (masalan: <code>snake</code> yoki <code>.html</code>):",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(PMSearchStates.waiting_name)
async def msg_pm_srch_name(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    query = (m.text or "").strip()
    if not query:
        await m.answer("So'rov bo'sh.", reply_markup=_cancel_kb())
        return

    sent = await m.answer(f"🔍 <code>{query}</code> qidirilmoqda...", parse_mode="HTML")
    results = await asyncio.to_thread(_search_by_name, _BASE, query)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_SEARCH),
    ]])
    if results:
        lines = [f"🔍 <b>Natijalar:</b> «{query}» — {len(results)} ta fayl\n"]
        for r in results:
            lines.append(f"• <code>{r}</code>")
        text = "\n".join(lines)
    else:
        text = f"🔍 «<code>{query}</code>» bo'yicha hech narsa topilmadi."

    await sent.edit_text(text[:_TG_MAX], reply_markup=back_kb, parse_mode="HTML")
    await log_action(m.from_user.id, "PM_SEARCH_NAME", query, f"found={len(results)}")


# ── Search text in files ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_PM_SRCH_TEXT)
async def cb_pm_srch_text_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(PMSearchStates.waiting_text)
    await q.answer()
    await q.message.edit_text(
        "📝 <b>Matn bo'yicha qidirish</b>\n\n"
        "Fayllar ichidan qidiruv so'zini yozing\n"
        "(masalan: <code>def handle</code> yoki <code>import asyncpg</code>):",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(PMSearchStates.waiting_text)
async def msg_pm_srch_text(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    query = (m.text or "").strip()
    if not query:
        await m.answer("So'rov bo'sh.", reply_markup=_cancel_kb())
        return

    sent = await m.answer(f"🔍 Fayllar ichidan <code>{query}</code> qidirilmoqda...", parse_mode="HTML")
    results = await asyncio.to_thread(_search_in_files, _BASE, query)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_SEARCH),
    ]])
    if results:
        lines = [f"📝 <b>Natijalar:</b> «{query}» — {len(results)} ta qator\n"]
        for rel_path, lineno, line_text in results:
            lines.append(f"<code>{rel_path}:{lineno}</code>")
            lines.append(f"  <i>{line_text}</i>")
        text = "\n".join(lines)
    else:
        text = f"📝 «<code>{query}</code>» fayllar ichida topilmadi."

    for i in range(0, len(text), _TG_MAX):
        chunk = text[i: i + _TG_MAX]
        kb = back_kb if i + _TG_MAX >= len(text) else None
        await m.answer(chunk, reply_markup=kb, parse_mode="HTML")

    await log_action(m.from_user.id, "PM_SEARCH_TEXT", query, f"found={len(results)}")


# ════════════════════════════════════════════════════════════════════════════
# 🧹 Maintenance — sub-menu
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_PM_MAINT)
async def cb_pm_maint_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🧹 <b>Xizmat</b>\n\n"
        "• <b>__pycache__ tozalash</b> — compiled bytecode fayllarini o'chirish\n"
        "• <b>Vaqtinchalik fayllar</b> — .pyc/.pyo va eski ZIP fayllarni o'chirish\n"
        "• <b>Disk foydalanish</b> — papkalar bo'yicha hajm (o'qish)",
        reply_markup=_maint_kb(),
        parse_mode="HTML",
    )


# ── Clear __pycache__ ─────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_PM_PYCACHE)
async def cb_pm_pycache_preview(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    dirs = await asyncio.to_thread(_find_pycache, _BASE)
    total_size = 0
    for d in dirs:
        for f in d.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size

    await state.set_state(PMConfirmStates.confirm_pycache)
    await q.message.edit_text(
        "🗑 <b>__pycache__ tozalash</b>\n\n"
        f"Topilgan papkalar: <b>{len(dirs)}</b>\n"
        f"Umumiy hajm:       <b>{_fmt_size(total_size)}</b>\n\n"
        "Barcha <code>__pycache__</code> papkalari o'chiriladi.\n"
        "Python ularni keyingi ishga tushirishda qayta yaratadi.\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(DEV_PM_PYCACHE_OK),
        parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == DEV_PM_PYCACHE_OK,
    StateFilter(PMConfirmStates.confirm_pycache),
)
async def cb_pm_pycache_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text("⏳ O'chirilmoqda...")

    def _do_clear() -> tuple[int, int]:
        dirs  = _find_pycache(_BASE)
        count = len(dirs)
        freed = 0
        for d in dirs:
            for f in d.rglob("*"):
                if f.is_file():
                    freed += f.stat().st_size
            shutil.rmtree(str(d), ignore_errors=True)
        return count, freed

    try:
        count, freed = await asyncio.to_thread(_do_clear)
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_MAINT),
        ]])
        await q.message.edit_text(
            f"✅ <b>__pycache__ tozalandi</b>\n\n"
            f"O'chirilgan papkalar: {count}\n"
            f"Bo'shatilgan joy:     {_fmt_size(freed)}",
            reply_markup=back_kb,
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PM_PYCACHE_CLEAR", str(_BASE), f"dirs={count} freed={_fmt_size(freed)}")
    except Exception as exc:
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_MAINT),
        ]])
        await q.message.edit_text(
            f"❌ Xato: <code>{exc}</code>",
            reply_markup=back_kb,
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PM_PYCACHE_CLEAR", str(_BASE), f"error:{exc}")


# ── Remove temp files ─────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_PM_TEMP)
async def cb_pm_temp_preview(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    files = await asyncio.to_thread(_find_temp_files, _BASE)
    total_size = sum(f.stat().st_size for f in files if f.exists())

    await state.set_state(PMConfirmStates.confirm_temp)
    sample = "\n".join(
        f"• <code>{f.relative_to(_BASE)}</code>" for f in files[:10]
    )
    if len(files) > 10:
        sample += f"\n  ... va {len(files) - 10} ta boshqa"

    await q.message.edit_text(
        "🧹 <b>Vaqtinchalik fayllar</b>\n\n"
        f"Topilgan fayllar: <b>{len(files)}</b>\n"
        f"Umumiy hajm:      <b>{_fmt_size(total_size)}</b>\n\n"
        f"{sample}\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(DEV_PM_TEMP_OK),
        parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == DEV_PM_TEMP_OK,
    StateFilter(PMConfirmStates.confirm_temp),
)
async def cb_pm_temp_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text("⏳ O'chirilmoqda...")

    def _do_remove() -> tuple[int, int]:
        files = _find_temp_files(_BASE)
        removed = 0
        freed   = 0
        for f in files:
            try:
                sz = f.stat().st_size
                f.unlink()
                removed += 1
                freed   += sz
            except Exception:
                pass
        return removed, freed

    try:
        removed, freed = await asyncio.to_thread(_do_remove)
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_MAINT),
        ]])
        await q.message.edit_text(
            f"✅ <b>Vaqtinchalik fayllar o'chirildi</b>\n\n"
            f"O'chirilgan fayllar: {removed}\n"
            f"Bo'shatilgan joy:    {_fmt_size(freed)}",
            reply_markup=back_kb,
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PM_TEMP_REMOVE", str(_BASE), f"files={removed} freed={_fmt_size(freed)}")
    except Exception as exc:
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_MAINT),
        ]])
        await q.message.edit_text(
            f"❌ Xato: <code>{exc}</code>",
            reply_markup=back_kb,
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PM_TEMP_REMOVE", str(_BASE), f"error:{exc}")


# ── Disk usage ────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_PM_DISK)
async def cb_pm_disk(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("⏳ Disk hajmi hisoblanmoqda...")

    entries = await asyncio.to_thread(_disk_usage, _BASE)
    total   = sum(sz for _, sz in entries)

    lines = ["💾 <b>Disk foydalanishi — gamehub/</b>\n"]
    for name, size in entries[:20]:
        bar_len = int(size / max(total, 1) * 16)
        bar     = "█" * bar_len + "░" * (16 - bar_len)
        lines.append(f"{bar}  {_fmt_size(size):>9}  {name}")
    lines.append(f"\n<b>Jami:</b> {_fmt_size(total)}")

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PM_MAINT),
    ]])
    await q.message.edit_text(
        "<pre>" + "\n".join(lines) + "</pre>",
        reply_markup=back_kb,
        parse_mode="HTML",
    )
    await log_action(q.from_user.id, "PM_DISK", str(_BASE), f"total={_fmt_size(total)}")


# ════════════════════════════════════════════════════════════════════════════
# 📦 Export — ZIP archive
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_PM_EXPORT)
async def cb_pm_export_preview(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()

    file_cnt = sum(
        1 for p in _BASE.rglob("*")
        if p.is_file()
        and not any(skip in p.parts for skip in _SKIP_DIRS | {"backups", "logs"})
        and p.suffix not in _SKIP_EXT
    )
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"gamehub_export_{ts}.zip"

    await state.update_data(zip_name=zip_name)
    await state.set_state(PMConfirmStates.confirm_export)
    await q.message.edit_text(
        "📦 <b>ZIP Eksport</b>\n\n"
        f"Arxiv nomi:   <code>{zip_name}</code>\n"
        f"Fayllar soni: <b>{file_cnt:,}</b>\n\n"
        "• <code>__pycache__</code>, <code>backups/</code>, <code>logs/</code> o'tkazib yuboriladi\n"
        "• ZIP yaratilgandan so'ng Telegram fayl sifatida yuboriladi\n"
        "• Telegram cheklovi: 50 MB\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(DEV_PM_EXPORT_OK),
        parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == DEV_PM_EXPORT_OK,
    StateFilter(PMConfirmStates.confirm_export),
)
async def cb_pm_export_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data     = await state.get_data()
    zip_name = data.get("zip_name", f"gamehub_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    await state.clear()
    await q.answer()

    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = _BACKUP_DIR / zip_name

    await q.message.edit_text(
        "⏳ <b>ZIP yaratilmoqda...</b>\n\n"
        "Bu bir necha soniya vaqt olishi mumkin.",
        parse_mode="HTML",
    )

    try:
        count = await asyncio.to_thread(_create_zip, _BASE, dest)
        size  = dest.stat().st_size
        size_mb = size / 1_048_576

        if size_mb > 50:
            back_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER),
            ]])
            await q.message.edit_text(
                f"⚠️ <b>ZIP yaratildi, lekin hajm juda katta</b>\n\n"
                f"Fayl: <code>{zip_name}</code>\n"
                f"Hajm: {size_mb:.2f} MB  (Telegram chegarasi: 50 MB)\n\n"
                f"Fayl <code>backups/{zip_name}</code> ga saqlandi.",
                reply_markup=back_kb,
                parse_mode="HTML",
            )
            await log_action(q.from_user.id, "PM_EXPORT", zip_name, f"too_large={size_mb:.1f}MB")
            return

        await q.message.edit_text(
            f"✅ <b>ZIP tayyor</b> — yuborilmoqda...\n\n"
            f"Fayllar: {count:,}\n"
            f"Hajm:    {size_mb:.2f} MB",
            parse_mode="HTML",
        )

        doc = FSInputFile(str(dest), filename=zip_name)
        await q.message.answer_document(
            doc,
            caption=(
                f"📦 <b>{zip_name}</b>\n"
                f"Fayllar: {count:,} | Hajm: {size_mb:.2f} MB\n"
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            parse_mode="HTML",
        )

        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER),
        ]])
        await q.message.edit_text(
            f"✅ <b>Eksport muvaffaqiyatli</b>\n\n"
            f"Fayl: <code>{zip_name}</code>\n"
            f"Fayllar: {count:,}\n"
            f"Hajm: {size_mb:.2f} MB",
            reply_markup=back_kb,
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PM_EXPORT", zip_name, f"{size_mb:.2f}MB/{count}files")

    except Exception as exc:
        logger.exception("PM_EXPORT failed: %s", exc)
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER),
        ]])
        await q.message.edit_text(
            f"❌ Eksport xatosi: <code>{exc}</code>",
            reply_markup=back_kb,
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "PM_EXPORT", zip_name, f"error:{exc}")
        if dest.exists():
            dest.unlink(missing_ok=True)
