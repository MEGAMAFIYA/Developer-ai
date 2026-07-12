"""Developer Mode › 🔄 Backup

Future features:
  - Dump global DB (games table) as SQL / JSON and send to admin
  - Dump game DB (scores, diamonds) as CSV
  - Schedule automatic daily backup to Telegram Saved Messages
  - Restore from a previously sent backup document
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.developer.callbacks import DEV_BACKUP
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:backup")

_TEXT = (
    "🔄 <b>Backup</b>\n\n"
    "Bu bo'limda ma'lumotlar bazasining zaxira nusxasini\n"
    "yaratish va tiklash mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_BACKUP)
async def cb_backup(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
