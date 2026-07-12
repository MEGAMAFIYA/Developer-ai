"""Developer Mode › 🤖 AI Developer

Future features:
  - Natural-language code generation (OpenAI / Gemini)
  - Ask AI about codebase
  - Auto-generate game descriptions
  - AI-powered bug triage from logs
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.developer.callbacks import DEV_AI
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:ai")

_TEXT = (
    "🤖 <b>AI Developer</b>\n\n"
    "Bu bo'limda sun'iy intellekt yordamida kod yozish,\n"
    "xatolarni topish va loyihani tahlil qilish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_AI)
async def cb_ai(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
