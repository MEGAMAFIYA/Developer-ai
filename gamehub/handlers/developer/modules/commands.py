"""Developer Mode › 🤖 Buyruqlar

Future features:
  - List all registered bot commands
  - Set / delete bot commands via setMyCommands
  - Toggle command availability per chat type
  - Reload handlers without full restart
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

import config as cfg
from handlers.developer.callbacks import DEV_COMMANDS
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:commands")


def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


_TEXT = (
    "🤖 <b>Buyruqlar</b>\n\n"
    "Bu bo'limda bot buyruqlarini ko'rish, qo'shish\n"
    "va o'chirish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_COMMANDS)
async def cb_commands(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
