"""Developer Mode › 🗄 Database

Future features:
  - Show table row counts (games, scores, diamonds)
  - Run read-only SQL queries
  - Export table as CSV and send to admin
  - Vacuum / analyse tables
  - Show pool connection stats
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

import config as cfg
from handlers.developer.callbacks import DEV_DATABASE
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:database")


def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


_TEXT = (
    "🗄 <b>Database</b>\n\n"
    "Bu bo'limda ma'lumotlar bazasini ko'rish, so'rovlar\n"
    "yuborish va eksport qilish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_DATABASE)
async def cb_database(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
