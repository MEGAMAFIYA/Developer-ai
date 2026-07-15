"""Developer Mode › 🤖 Buyruqlar Menejeri

Features
────────
📋 Ro'yxat        — joriy buyruqlarni ko'rish
✅ O'rnatish       — standart buyruqlar to'plamini o'rnatish (tasdiq kerak)
🗑 Tozalash        — barcha buyruqlarni o'chirish (tasdiq kerak)
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config as cfg
from handlers.developer.callbacks import (
    DEV_COMMANDS,
    DEV_CMD_LIST,
    DEV_CMD_SET,
    DEV_CMD_SET_OK,
    DEV_CMD_CLEAR,
    DEV_CMD_CLEAR_OK,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:commands")

_TG_MAX = 4096

# Standard command set for this bot
_DEFAULT_COMMANDS: list[tuple[str, str]] = [
    ("start",     "Botni ishga tushirish"),
    ("help",      "Yordam va qo'llanma"),
    ("games",     "O'yinlar ro'yxati"),
    ("top",       "Reytinglar"),
    ("profile",   "Profilim"),
    ("developer", "Developer Mode (admin)"),
]


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _cmd_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Ko'rish",         callback_data=DEV_CMD_LIST),
            InlineKeyboardButton(text="✅ O'rnatish",        callback_data=DEV_CMD_SET),
        ],
        [
            InlineKeyboardButton(text="🗑 Tozalash",         callback_data=DEV_CMD_CLEAR),
            InlineKeyboardButton(text="⬅️ Orqaga",           callback_data="dev:menu"),
        ],
    ])


def _confirm_set_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, o'rnatish",    callback_data=DEV_CMD_SET_OK),
        InlineKeyboardButton(text="❌ Bekor",             callback_data=DEV_COMMANDS),
    ]])


def _confirm_clear_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Ha, tozalash",     callback_data=DEV_CMD_CLEAR_OK),
        InlineKeyboardButton(text="❌ Bekor",             callback_data=DEV_COMMANDS),
    ]])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_commands(bot) -> list[BotCommand]:
    try:
        return await bot.get_my_commands()
    except Exception as exc:
        logger.error("get_my_commands error: %s", exc)
        return []


def _fmt_commands(cmds: list[BotCommand]) -> str:
    if not cmds:
        return "📋 <b>Buyruqlar</b>\n\nHech qanday buyruq o'rnatilmagan."
    lines = [f"📋 <b>Joriy buyruqlar ({len(cmds)} ta)</b>\n"]
    for c in cmds:
        lines.append(f"/{c.command} — {c.description}")
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_COMMANDS)
async def cb_commands_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🤖 <b>Buyruqlar Menejeri</b>\n\n"
        "Bot buyruqlarini ko'rish, o'rnatish va tozalash.",
        reply_markup=_cmd_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_CMD_LIST)
async def cb_cmd_list(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    cmds = await _get_commands(q.bot)
    text = _fmt_commands(cmds)
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_cmd_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_CMD_SET)
async def cb_cmd_set_confirm(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    lines = ["✅ <b>Standart buyruqlarni o'rnatish</b>\n\nQuyidagi buyruqlar o'rnatiladi:\n"]
    for cmd, desc in _DEFAULT_COMMANDS:
        lines.append(f"/{cmd} — {desc}")
    lines.append("\nDavom etasizmi?")
    await q.message.edit_text(
        "\n".join(lines),
        reply_markup=_confirm_set_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_CMD_SET_OK)
async def cb_cmd_set_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ O'rnatilmoqda…")
    try:
        bot_cmds = [BotCommand(command=cmd, description=desc)
                    for cmd, desc in _DEFAULT_COMMANDS]
        await q.bot.set_my_commands(bot_cmds)
        await log_action(
            q.from_user.id, "CMD_SET",
            ", ".join(f"/{c}" for c, _ in _DEFAULT_COMMANDS), "ok"
        )
        cmds = await _get_commands(q.bot)
        await q.message.edit_text(
            f"✅ {len(bot_cmds)} ta buyruq o'rnatildi!\n\n" + _fmt_commands(cmds)[:3500],
            reply_markup=_cmd_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("set_my_commands error: %s", exc)
        await q.message.edit_text(
            f"❌ O'rnatishda xato: {exc}",
            reply_markup=_cmd_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(lambda c: c.data == DEV_CMD_CLEAR)
async def cb_cmd_clear_confirm(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🗑 <b>Buyruqlarni tozalash</b>\n\n"
        "Barcha bot buyruqlari o'chiriladi.\n"
        "⚠️ Bu amalni qaytarib bo'lmaydi!\n\nDavom etasizmi?",
        reply_markup=_confirm_clear_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_CMD_CLEAR_OK)
async def cb_cmd_clear_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Tozalanmoqda…")
    try:
        await q.bot.delete_my_commands()
        await log_action(q.from_user.id, "CMD_CLEAR", "all", "ok")
        await q.message.edit_text(
            "✅ Barcha buyruqlar o'chirildi.",
            reply_markup=_cmd_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("delete_my_commands error: %s", exc)
        await q.message.edit_text(
            f"❌ Tozalashda xato: {exc}",
            reply_markup=_cmd_keyboard(),
            parse_mode="HTML",
        )
