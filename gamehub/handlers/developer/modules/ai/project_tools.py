"""AI Developer project tools backed exclusively by GitHub."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import config as cfg
from handlers.developer.modules.ai import services
from handlers.developer.modules.ai.action_log import log_action
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL, AI_MENU, AI_PROJ_MANAGER, AI_PROJ_SCAN, AI_PROJ_MAP,
    AI_PROJ_TEST, AI_PROJ_BACKUP, AI_PROJ_OK,
)
from services.project_provider import get_project_provider

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:project_tools")
_TG_MAX = 4096


class ProjStates(StatesGroup):
    confirming = State()


def _guard(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard_cb(q: CallbackQuery) -> bool:
    if _guard(q.from_user.id):
        return True
    await q.answer("Ruxsat yo'q.", show_alert=True)
    return False


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔎 AI Audit", callback_data=AI_PROJ_SCAN),
            InlineKeyboardButton(text="📋 Fayl xaritasi", callback_data=AI_PROJ_MAP),
        ],
        [
            InlineKeyboardButton(text="🧪 Sintaksis test", callback_data=AI_PROJ_TEST),
            InlineKeyboardButton(text="📦 Backup", callback_data=AI_PROJ_BACKUP),
        ],
        [InlineKeyboardButton(text="⬅️ AI Menyu", callback_data=AI_MENU)],
    ])


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash", callback_data=AI_PROJ_OK),
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])


def _esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@router.callback_query(lambda c: c.data == AI_PROJ_MANAGER)
async def cb_proj_manager_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🔧 <b>Project Manager</b>\n\n"
        "AI audit, GitHub repository xaritasi, test va ZIP eksport.",
        reply_markup=_menu_kb(), parse_mode="HTML",
    )


async def _context(max_chars: int = 6000) -> str:
    provider = get_project_provider()
    entries = [e for e in await provider.tree() if e.kind == "file" and e.path.endswith(".py")]
    chunks: list[str] = []
    total = 0
    for entry in entries:
        if total >= max_chars:
            break
        try:
            text = (await provider.get_file(entry.path, preserve_repository_root=True)).content[:2000]
        except Exception:
            continue
        chunks.append(f"### {entry.path}\n```python\n{text}\n```")
        total += len(text)
    return "\n\n".join(chunks)


@router.callback_query(lambda c: c.data == AI_PROJ_SCAN)
async def cb_proj_scan(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("GitHub loyihasi AI tomonidan skanerlanmoqda...")
    prompt = (
        "Quyidagi GitHub repository Python/HTML5 kodini professional audit qil:\n\n"
        f"{await _context()}\n\n"
        "Hisobotni o'zbek tilida kritik xatolar, xavfsizlik, optimizatsiya va umumiy baho bo'limlarida yoz."
    )
    result = await services.get_manager().generate_text(prompt)
    text = f"<b>Loyiha auditi</b>\n\n{result.content}" if result.ok else f"<b>AI xatosi</b>\n\n<code>{_esc(result.error or '')}</code>"
    for index in range(0, len(text), _TG_MAX):
        await q.message.answer(text[index:index + _TG_MAX], reply_markup=_back_kb() if index + _TG_MAX >= len(text) else None, parse_mode="HTML")
    await log_action(q.from_user.id, "PROJ_SCAN", "github repository", "ok" if result.ok else "ai_error")


@router.callback_query(lambda c: c.data == AI_PROJ_MAP)
async def cb_proj_map(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    entries = await get_project_provider().tree()
    lines = ["repository/"]
    for entry in entries:
        parts = entry.path.split("/")
        lines.append(f"{'  ' * (len(parts) - 1)}{'📁 ' if entry.kind == 'dir' else '📄 '}{parts[-1]} ({entry.size:,} B)" if entry.kind == "file" else f"{'  ' * (len(parts) - 1)}📁 {parts[-1]}/")
    await q.message.edit_text(
        f"<b>GitHub fayllar xaritasi</b>\n\n<pre>{_esc(chr(10).join(lines))[:3500]}</pre>",
        reply_markup=_back_kb(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_PROJ_TEST)
async def cb_proj_test(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    entries = [e for e in await get_project_provider().tree() if e.kind == "file" and e.path.endswith(".py")]
    ok_count = 0
    errors: list[str] = []
    for entry in entries:
        try:
            compile((await get_project_provider().get_file(entry.path, preserve_repository_root=True)).content, entry.path, "exec")
            ok_count += 1
        except Exception as exc:
            errors.append(f"{entry.path}: {exc}")
    if errors:
        body = f"<b>GitHub Python test — xatolar</b>\n\nTekshirildi: {len(entries)}\nMuvaffaqiyatli: {ok_count}\nXatolar: {len(errors)}\n\n<pre>{_esc(chr(10).join(errors[:20]))[:2000]}</pre>"
    else:
        body = f"<b>GitHub Python test — MUVAFFAQIYATLI</b>\n\nTekshirildi: {len(entries)}\nXatolar: 0"
    await q.message.edit_text(body, reply_markup=_back_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == AI_PROJ_BACKUP)
async def cb_proj_backup_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    entries = [e for e in await get_project_provider().tree() if e.kind == "file"]
    name = f"github_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    await state.update_data(zip_name=name, count=len(entries))
    await state.set_state(ProjStates.confirming)
    await q.answer()
    await q.message.edit_text(
        f"<b>GitHub backup — preview</b>\n\nFayllar: {len(entries)}\nArxiv: <code>{name}</code>\n\nTasdiqlaysizmi?",
        reply_markup=_confirm_kb(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_PROJ_OK, StateFilter(ProjStates.confirming))
async def cb_proj_backup_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    await state.clear()
    await q.answer()
    try:
        raw = await get_project_provider().export_zip()
        name = data.get("zip_name", "github_backup.zip")
        await q.message.answer_document(BufferedInputFile(raw, filename=name), caption=f"📦 {name} ({len(raw):,} B)")
        await q.message.edit_text("✅ GitHub backup tayyor.", reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(q.from_user.id, "PROJ_BACKUP", name, f"bytes={len(raw)}")
    except Exception as exc:
        await q.message.edit_text(f"❌ Backup xatosi: <code>{_esc(str(exc))}</code>", reply_markup=_back_kb(), parse_mode="HTML")