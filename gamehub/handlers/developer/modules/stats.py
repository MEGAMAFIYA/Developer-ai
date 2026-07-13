"""Developer Mode › 📊 Statistika

Future features:
  - Total users, active users (last 7 / 30 days)
  - Scores submitted per day chart
  - Top games by play count
  - Diamond balance overview
  - Bot uptime
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

import config as cfg
from handlers.developer.callbacks import DEV_STATS
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:stats")


def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


_TEXT = (
    "📊 <b>Statistika</b>\n\n"
    "Bu bo'limda foydalanuvchilar soni, o'yinlar faolligi\n"
    "va boshqa muhim ko'rsatkichlarni ko'rish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_STATS)
async def cb_stats(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
