"""Developer Mode › 🧪 Test

Future features:
  - Send a test score submission (simulate WebApp call)
  - Check DB connectivity (ping both pools)
  - Verify WEBAPP_URL is reachable
  - Test photo upload pipeline
  - Run a dry-run of /yangi seeding
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.developer.callbacks import DEV_TEST
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:test")

_TEXT = (
    "🧪 <b>Test</b>\n\n"
    "Bu bo'limda bot funksiyalarini sinab ko'rish,\n"
    "ulanishlarni tekshirish va debug qilish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_TEST)
async def cb_test(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
