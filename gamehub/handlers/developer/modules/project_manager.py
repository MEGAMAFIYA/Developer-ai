"""Developer Mode › Project Manager.

Project data is read from the configured GitHub repository.  Runtime metadata
(Python version and process start time) is the only local information exposed.
The callback names and FSM state groups remain compatible with the old UI.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
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
from handlers.developer.modules.ai.action_log import log_action
from services.project_provider import ProjectProviderError, get_project_provider

logger = logging.getLogger(__name__)
router = Router(name="dev:project_manager")
_TG_MAX = 4096
_TEXT_EXTS = {".py", ".html", ".js", ".css", ".json", ".md", ".txt", ".yaml", ".yml", ".toml"}


class PMSearchStates(StatesGroup):
    waiting_name = State()
    waiting_text = State()


class PMConfirmStates(StatesGroup):
    confirm_pycache = State()
    confirm_temp = State()
    confirm_export = State()


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


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📂 Ma'lumot", callback_data=DEV_PM_INFO),
            InlineKeyboardButton(text="📊 Statistika", callback_data=DEV_PM_STATS),
        ],
        [
            InlineKeyboardButton(text="🔍 Qidirish", callback_data=DEV_PM_SEARCH),
            InlineKeyboardButton(text="🧹 Xizmat", callback_data=DEV_PM_MAINT),
        ],
        [InlineKeyboardButton(text="📦 Eksport (ZIP)", callback_data=DEV_PM_EXPORT)],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="dev:menu")],
    ])


def _search_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 Fayl nomi bo'yicha", callback_data=DEV_PM_SRCH_NAME),
            InlineKeyboardButton(text="📝 Matn bo'yicha", callback_data=DEV_PM_SRCH_TEXT),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER)],
    ])


def _maint_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 __pycache__ tozalash", callback_data=DEV_PM_PYCACHE),
            InlineKeyboardButton(text="🧹 Vaqtinchalik fayllar", callback_data=DEV_PM_TEMP),
        ],
        [InlineKeyboardButton(text="💾 Disk foydalanish", callback_data=DEV_PM_DISK)],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_PROJECT_MANAGER)],
    ])


def _confirm_kb(ok_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=ok_cb),
        InlineKeyboardButton(text="❌ Bekor", callback_data=DEV_PROJECT_MANAGER),
    ]])


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=DEV_PROJECT_MANAGER),
    ]])


def _fmt_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _get_process_start() -> str:
    try:
        pid = os.getpid()
        with open(f"/proc/{pid}/stat", encoding="utf-8") as proc_stat:
            fields = proc_stat.read().split(")", 1)[1].split()
        start_ticks = int(fields[19])
        clk_tck = os.sysconf("SC_CLK_TCK")
        with open("/proc/uptime", encoding="utf-8") as uptime_file:
            uptime_s = float(uptime_file.read().split()[0])
        start_epoch = time.time() - uptime_s + start_ticks / clk_tck
        return datetime.fromtimestamp(start_epoch).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "(aniqlanmadi)"


def _back(callback: str = DEV_PROJECT_MANAGER) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=callback),
    ]])


async def _entries():
    return await get_project_provider().tree()


async def _stats() -> tuple[dict[str, int], int, int, int]:
    entries = [entry for entry in await _entries() if entry.kind == "file"]
    counts: Counter[str] = Counter()
    total_size = 0
    for entry in entries:
        ext = entry.path.rsplit(".", 1)[-1].lower() if "." in entry.path.rsplit("/", 1)[-1] else ""
        ext = f".{ext}" if ext else ""
        total_size += entry.size
        if ext == ".py":
            label = "Python (.py)"
        elif ext == ".html":
            label = "HTML (.html)"
        elif ext == ".css":
            label = "CSS (.css)"
        elif ext == ".js":
            label = "JavaScript (.js)"
        elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"}:
            label = "Rasmlar"
        elif ext in {".db", ".sqlite", ".sqlite3"}:
            label = "Ma'lumotlar bazasi"
        else:
            label = "Boshqa"
        counts[label] += 1
    dirs = len({"/".join(entry.path.split("/")[:-1]) for entry in await _entries()
                if entry.kind == "file" and "/" in entry.path})
    return dict(counts), len(entries), dirs, total_size


@router.callback_query(lambda c: c.data == DEV_PROJECT_MANAGER)
async def cb_pm_main(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "📦 <b>Project Manager</b>\n\n"
        "GitHub repository manbasi bilan ishlaydi.\n\n"
        "• Ma'lumot — repo statistikasi va runtime metadata\n"
        "• Statistika — fayllar turi bo'yicha\n"
        "• Qidirish — fayl nomi yoki matn bo'yicha\n"
        "• Xizmat — Render fayllariga tegmaydi\n"
        "• Eksport — GitHub ZIP arxivi",
        reply_markup=_main_kb(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_PM_INFO)
async def cb_pm_info(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("⏳ GitHub ma'lumotlari olinmoqda...", parse_mode="HTML")
    try:
        provider = get_project_provider()
        counts, files, dirs, total = await _stats()
        label = await provider.repository_label()
        text = (
            "📂 <b>Loyiha ma'lumoti</b>\n\n"
            f"<b>Repository:</b> <code>{label}</code>\n"
            f"<b>Jami fayllar:</b> {files:,}\n"
            f"<b>Papkalar:</b> {dirs:,}\n"
            f"<b>Umumiy hajm:</b> {_fmt_size(total)}\n"
            f"<b>Python runtime:</b> {sys.version.split()[0]}\n"
            f"<b>So'nggi restart:</b> {_get_process_start()}"
        )
        await q.message.edit_text(text, reply_markup=_back(), parse_mode="HTML")
        await log_action(q.from_user.id, "PM_INFO", label, "ok")
    except Exception as exc:
        await q.message.edit_text(f"❌ GitHub xatosi: <code>{exc}</code>", reply_markup=_back(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_PM_STATS)
async def cb_pm_stats(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    try:
        counts, files, _, _ = await _stats()
        lines = ["📊 <b>GitHub fayl statistikasi</b>\n"]
        for label, count in sorted(counts.items()):
            pct = count / max(files, 1) * 100
            lines.append(f"<b>{label}</b>\n{'█' * int(pct / 5)}{'░' * (20 - int(pct / 5))} {count:,} ({pct:.1f}%)\n")
        lines.append(f"\n<b>Jami:</b> {files:,} fayl")
        await q.message.edit_text("\n".join(lines), reply_markup=_back(), parse_mode="HTML")
    except Exception as exc:
        await q.message.edit_text(f"❌ GitHub xatosi: <code>{exc}</code>", reply_markup=_back(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_PM_SEARCH)
async def cb_pm_search_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🔍 <b>GitHub qidiruvi</b>\n\nFayl nomi yoki repository ichidagi matnni qidiring.",
        reply_markup=_search_kb(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_PM_SRCH_NAME)
async def cb_pm_srch_name_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(PMSearchStates.waiting_name)
    await q.answer()
    await q.message.edit_text("📄 Qidiruv so'zini yozing:", reply_markup=_cancel_kb())


@router.message(PMSearchStates.waiting_name)
async def msg_pm_srch_name(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    query = (m.text or "").strip()
    try:
        results = await get_project_provider().search_name(query, 40)
        text = (f"🔍 <b>Natijalar:</b> «{query}» — {len(results)} ta fayl\n\n" +
                "\n".join(f"• <code>{path}</code>" for path in results)) if results else f"🔍 «{query}» topilmadi."
        await m.answer(text[:_TG_MAX], reply_markup=_back(DEV_PM_SEARCH), parse_mode="HTML")
    except Exception as exc:
        await m.answer(f"❌ GitHub xatosi: <code>{exc}</code>", reply_markup=_back(DEV_PM_SEARCH), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_PM_SRCH_TEXT)
async def cb_pm_srch_text_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(PMSearchStates.waiting_text)
    await q.answer()
    await q.message.edit_text("📝 Repository ichidan qidiriladigan matnni yozing:", reply_markup=_cancel_kb())


@router.message(PMSearchStates.waiting_text)
async def msg_pm_srch_text(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    query = (m.text or "").strip()
    try:
        results = await get_project_provider().search_text(query, extensions=_TEXT_EXTS, limit=20)
        text = (f"📝 <b>Natijalar:</b> «{query}» — {len(results)} ta qator\n\n" +
                "\n".join(f"<code>{p}:{n}</code>\n  <i>{line}</i>" for p, n, line in results)) if results else f"📝 «{query}» topilmadi."
        for index in range(0, len(text), _TG_MAX):
            await m.answer(text[index:index + _TG_MAX], reply_markup=_back(DEV_PM_SEARCH) if index + _TG_MAX >= len(text) else None, parse_mode="HTML")
    except Exception as exc:
        await m.answer(f"❌ GitHub xatosi: <code>{exc}</code>", reply_markup=_back(DEV_PM_SEARCH), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_PM_MAINT)
async def cb_pm_maint_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🧹 <b>Xizmat</b>\n\n"
        "GitHub-only rejimda Render __pycache__, vaqtinchalik fayl va disk ma'lumotlariga kirilmaydi.\n"
        "Eksport GitHub repository orqali bajariladi.",
        reply_markup=_maint_kb(), parse_mode="HTML",
    )


async def _runtime_only_unavailable(q: CallbackQuery, title: str) -> None:
    await q.answer("GitHub-only rejim", show_alert=True)
    await q.message.edit_text(
        f"ℹ️ <b>{title}</b>\n\nBu amal Render/local fayl tizimiga tegishni talab qiladi va GitHub-only rejimda o'chirilgan.",
        reply_markup=_back(DEV_PM_MAINT), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_PM_PYCACHE)
async def cb_pm_pycache_preview(q: CallbackQuery, state: FSMContext) -> None:
    await _runtime_only_unavailable(q, "__pycache__ tozalash")


@router.callback_query(lambda c: c.data == DEV_PM_PYCACHE_OK, StateFilter(PMConfirmStates.confirm_pycache))
async def cb_pm_pycache_confirm(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _runtime_only_unavailable(q, "__pycache__ tozalash")


@router.callback_query(lambda c: c.data == DEV_PM_TEMP)
async def cb_pm_temp_preview(q: CallbackQuery, state: FSMContext) -> None:
    await _runtime_only_unavailable(q, "Vaqtinchalik fayllar")


@router.callback_query(lambda c: c.data == DEV_PM_TEMP_OK, StateFilter(PMConfirmStates.confirm_temp))
async def cb_pm_temp_confirm(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _runtime_only_unavailable(q, "Vaqtinchalik fayllar")


@router.callback_query(lambda c: c.data == DEV_PM_DISK)
async def cb_pm_disk(q: CallbackQuery) -> None:
    await _runtime_only_unavailable(q, "Disk foydalanishi")


@router.callback_query(lambda c: c.data == DEV_PM_EXPORT)
async def cb_pm_export_preview(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    try:
        entries = [entry for entry in await _entries() if entry.kind == "file"]
        zip_name = f"github_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        await state.update_data(zip_name=zip_name)
        await state.set_state(PMConfirmStates.confirm_export)
        await q.answer()
        await q.message.edit_text(
            f"📦 <b>GitHub ZIP eksport</b>\n\nFayllar: <b>{len(entries):,}</b>\n"
            f"Arxiv: <code>{zip_name}</code>\n\nTasdiqlaysizmi?",
            reply_markup=_confirm_kb(DEV_PM_EXPORT_OK), parse_mode="HTML",
        )
    except Exception as exc:
        await q.answer("GitHub xatosi", show_alert=True)
        await q.message.edit_text(f"❌ <code>{exc}</code>", reply_markup=_back(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_PM_EXPORT_OK, StateFilter(PMConfirmStates.confirm_export))
async def cb_pm_export_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    await state.clear()
    await q.answer()
    await q.message.edit_text("⏳ GitHub ZIP yaratilmoqda...")
    try:
        raw = await get_project_provider().export_zip()
        filename = data.get("zip_name", "github_export.zip")
        await q.message.answer_document(
            BufferedInputFile(raw, filename=filename),
            caption=f"📦 {filename} | {_fmt_size(len(raw))}",
        )
        await q.message.edit_text("✅ GitHub eksport tayyor.", reply_markup=_back(), parse_mode="HTML")
        await log_action(q.from_user.id, "PM_EXPORT", filename, f"bytes={len(raw)}")
    except Exception as exc:
        await q.message.edit_text(f"❌ Eksport xatosi: <code>{exc}</code>", reply_markup=_back(), parse_mode="HTML")