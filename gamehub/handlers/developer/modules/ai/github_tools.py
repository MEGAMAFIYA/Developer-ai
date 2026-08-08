"""AI Developer GitHub Manager using the GitHub provider only."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config as cfg
from handlers.developer.modules.ai.action_log import log_action
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL, AI_MENU, AI_GH_MANAGER, AI_GH_CLONE, AI_GH_COMMIT,
    AI_GH_PUSH, AI_GH_PULL, AI_GH_OK,
)
from services.project_provider import get_project_provider

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:github_tools")


class GHStates(StatesGroup):
    waiting_input = State()
    confirming = State()


def _admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery | Message) -> bool:
    if _admin(q.from_user.id):
        return True
    if isinstance(q, CallbackQuery):
        await q.answer("Ruxsat yo'q.", show_alert=True)
    else:
        await q.answer("Ruxsat yo'q.")
    return False


def _cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])


def _confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash", callback_data=AI_GH_OK),
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])


def _back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Repository", callback_data=AI_GH_CLONE),
            InlineKeyboardButton(text="📤 Commit", callback_data=AI_GH_COMMIT),
        ],
        [
            InlineKeyboardButton(text="🚀 Push", callback_data=AI_GH_PUSH),
            InlineKeyboardButton(text="📥 Pull", callback_data=AI_GH_PULL),
        ],
        [InlineKeyboardButton(text="⬅️ AI Menyu", callback_data=AI_MENU)],
    ])


@router.callback_query(lambda c: c.data == AI_GH_MANAGER)
async def cb_gh_manager_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🐙 <b>GitHub Manager</b>\n\n"
        "GitHub repository yagona loyiha manbasi.\n"
        "Repository — konfiguratsiyani ko'rish, Commit — provider orqali commit qilish.\n"
        "Push/Pull local Git emas, GitHub API holatini yangilash/cache refresh sifatida ishlaydi.",
        reply_markup=_menu(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_GH_CLONE)
async def cb_gh_clone_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.update_data(operation="clone")
    await state.set_state(GHStates.confirming)
    label = await get_project_provider().repository_label()
    await q.message.edit_text(f"<b>Repository</b>\n\nJoriy repo: <code>{label}</code>\n\nYuklab olish/clone Render diskiga bajarilmaydi.", reply_markup=_confirm(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == AI_GH_COMMIT)
async def cb_gh_commit_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.update_data(operation="commit")
    await state.set_state(GHStates.waiting_input)
    await q.message.edit_text("GitHub commit xabarini yozing. Fayl o'zgarishlari alohida File Tools orqali commit qilinadi.", reply_markup=_cancel(), parse_mode="HTML")


@router.message(GHStates.waiting_input)
async def msg_gh_waiting_input(m: Message, state: FSMContext) -> None:
    if not await _guard(m):
        return
    data = await state.get_data()
    await state.update_data(input=(m.text or "").strip())
    await state.set_state(GHStates.confirming)
    await m.answer(f"<b>Commit preview</b>\n\nXabar: <code>{(m.text or '').strip()}</code>\n\nTasdiqlaysizmi?", reply_markup=_confirm(), parse_mode="HTML")


@router.callback_query(lambda c: c.data in (AI_GH_PUSH, AI_GH_PULL))
async def cb_gh_sync_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    op = "push" if q.data == AI_GH_PUSH else "pull"
    await state.update_data(operation=op)
    await state.set_state(GHStates.confirming)
    await q.answer()
    label = await get_project_provider().repository_label()
    await q.message.edit_text(f"<b>GitHub {op.upper()} preview</b>\n\n<code>{label}</code>\n\nRender/local Git ishlatilmaydi. Tasdiqlaysizmi?", reply_markup=_confirm(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == AI_GH_OK, StateFilter(GHStates.confirming))
async def cb_gh_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data = await state.get_data()
    op = data.get("operation", "")
    inp = data.get("input", "")
    await state.clear()
    await q.answer()
    try:
        provider = get_project_provider()
        if op in {"push", "pull"}:
            entries = await provider.refresh()
            result = f"GitHub cache yangilandi: {len(entries)} ta entry"
        elif op == "clone":
            result = f"Repository already configured: {await provider.repository_label()}"
        elif op == "commit":
            result = "GitHub Contents API commitlari File Tools amallarida yaratiladi."
        else:
            result = "Noma'lum amal"
        await q.message.edit_text(f"<b>{op.upper()} — tayyor</b>\n\n<pre>{result[:1500]}</pre>", reply_markup=_back(), parse_mode="HTML")
        await log_action(q.from_user.id, f"GH_{op.upper()}", inp[:100], "ok")
    except Exception as exc:
        await q.message.edit_text(f"Xato: <code>{exc}</code>", reply_markup=_back(), parse_mode="HTML")
        await log_action(q.from_user.id, f"GH_{op.upper()}", inp[:100], f"error:{exc}")