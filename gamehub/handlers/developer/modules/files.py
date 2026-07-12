"""Developer Mode › 📂 Fayllar

Future features:
  - Browse webapp/games/ directory
  - Upload / replace HTML game files via bot
  - Preview file contents
  - Delete or rename files
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.developer.callbacks import DEV_FILES
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:files")

_TEXT = (
    "📂 <b>Fayllar</b>\n\n"
    "Bu bo'limda server fayllarini ko'rish, yuklash\n"
    "va tahrirlash mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_FILES)
async def cb_files(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
