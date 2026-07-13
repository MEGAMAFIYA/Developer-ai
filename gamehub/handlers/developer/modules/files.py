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

import config as cfg
from handlers.developer.callbacks import DEV_FILES
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:files")


def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


_TEXT = (
    "📂 <b>Fayllar</b>\n\n"
    "Bu bo'limda server fayllarini ko'rish, yuklash\n"
    "va tahrirlash mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_FILES)
async def cb_files(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
