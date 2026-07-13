"""Developer Mode › ⚙️ Sozlamalar

Future features:
  - Toggle DIAMONDS_ENABLED flag
  - Set/view WEBAPP_URL at runtime
  - Manage ADMIN_ID list
  - Toggle maintenance mode (reject non-admin messages)
  - View / reload .env values (safe — no secrets shown)
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

import config as cfg
from handlers.developer.callbacks import DEV_SETTINGS
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:settings")


def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


_TEXT = (
    "⚙️ <b>Sozlamalar</b>\n\n"
    "Bu bo'limda bot sozlamalarini ko'rish va o'zgartirish\n"
    "mumkin bo'ladi (flags, URLs, rejimlar).\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_SETTINGS)
async def cb_settings(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
