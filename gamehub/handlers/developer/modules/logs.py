"""Developer Mode › 📜 Loglar

Future features:
  - Tail the last N lines of the application log
  - Filter logs by level (ERROR, WARNING, INFO)
  - Send log file as document
  - Clear log buffer
  - Set log level at runtime
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.developer.callbacks import DEV_LOGS
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:logs")

_TEXT = (
    "📜 <b>Loglar</b>\n\n"
    "Bu bo'limda real vaqtda log fayllarini ko'rish,\n"
    "filtr qilish va yuklab olish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_LOGS)
async def cb_logs(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
