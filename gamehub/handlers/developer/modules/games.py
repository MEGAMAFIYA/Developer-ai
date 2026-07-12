"""Developer Mode › 🎮 O'yinlar

Future features:
  - List all games with status (active/inactive)
  - Quick enable/disable toggle
  - View per-game score stats
  - Force-reseed initial games
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.developer.callbacks import DEV_GAMES
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:games")

_TEXT = (
    "🎮 <b>O'yinlar</b>\n\n"
    "Bu bo'limda barcha o'yinlarni boshqarish, faollashtirish,\n"
    "o'chirish va statistikasini ko'rish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_GAMES)
async def cb_games(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
