"""Developer Mode › 🌐 GitHub

Future features:
  - View latest commits on configured repo/branch
  - Trigger a deploy / pull via webhook
  - Create issues from bot
  - Browse open PRs
  - Diff viewer for recent changes
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

import config as cfg
from handlers.developer.callbacks import DEV_GITHUB
from handlers.developer.keyboards import back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:github")


def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


_TEXT = (
    "🌐 <b>GitHub</b>\n\n"
    "Bu bo'limda GitHub repozitoriyasini boshqarish,\n"
    "commitlarni ko'rish va deploy qilish mumkin bo'ladi.\n\n"
    "🚧 <i>Hozircha ishlab chiqilmoqda...</i>"
)


@router.callback_query(lambda c: c.data == DEV_GITHUB)
async def cb_github(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(_TEXT, reply_markup=back_keyboard(), parse_mode="HTML")
