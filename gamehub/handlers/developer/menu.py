"""Developer Mode — /developer command + main menu navigation."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config as cfg
from handlers.developer.callbacks import DEV_MENU, DEV_CLOSE
from handlers.developer.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:menu")

MENU_TEXT = (
    "🧑‍💻 <b>Developer Mode</b>\n\n"
    "Xush kelibsiz! Quyidagi bo'limlardan birini tanlang:"
)


# ── Guard: only ADMIN_ID may use this router ─────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


# ── /developer command ────────────────────────────────────────────────────────

@router.message(Command("developer"))
async def cmd_developer(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat administrator uchun.")
        return

    await message.answer(MENU_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")


# ── "Back to menu" callback (used by every sub-module) ───────────────────────

@router.callback_query(lambda c: c.data == DEV_MENU)
async def cb_back_to_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Clear any active AI FSM state when navigating back to the Developer main menu.

    Without this clear(), states such as AIChatStates.waiting_message would
    persist after the user leaves the AI sub-menu, causing subsequent messages
    to be routed to the wrong handler.
    """
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return

    await state.clear()
    await query.answer()
    await query.message.edit_text(
        MENU_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


# ── "Exit" callback ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_CLOSE)
async def cb_close(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return

    await query.answer("Developer Mode yopildi.")
    await query.message.delete()
