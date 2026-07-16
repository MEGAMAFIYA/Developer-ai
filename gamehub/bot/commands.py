"""Bot command registration via Telegram Bot API setMyCommands().

Called once during bot startup — no BotFather interaction required.

Scopes registered
─────────────────
• BotCommandScopeDefault          — public commands visible to all users
                                    in private chats and the menu button.
• BotCommandScopeAllGroupChats    — same public commands shown in every
                                    group/supergroup when a user types "/".
• BotCommandScopeChat (admin)     — full command list (public + admin)
                                    shown only in the admin's private chat.
"""

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from config import config

logger = logging.getLogger(__name__)

# ── Command lists ─────────────────────────────────────────────────────────────

# Commands every user sees in private chat and the menu button
_PUBLIC_COMMANDS: list[BotCommand] = [
    BotCommand(command="start",    description="🎮 Botni ishga tushirish"),
    BotCommand(command="oyinlar",  description="🕹 O'yinlar ro'yxatini ko'rish"),
    BotCommand(command="reyting",  description="🏆 Reyting va yuqori natijalar"),
]

# Extra commands visible only to the admin in their private chat
_ADMIN_ONLY_COMMANDS: list[BotCommand] = [
    BotCommand(command="yangi",     description="➕ Yangi o'yin qo'shish"),
    BotCommand(command="tuzatish",  description="✏️ O'yinni tahrirlash"),
    BotCommand(command="bekor",     description="❌ Amalni bekor qilish"),
    BotCommand(command="developer", description="🛠 Developer rejimi"),
]

_ADMIN_ALL_COMMANDS: list[BotCommand] = _PUBLIC_COMMANDS + _ADMIN_ONLY_COMMANDS

# Commands shown in group chats (keep short — no admin tools there)
_GROUP_COMMANDS: list[BotCommand] = [
    BotCommand(command="start",   description="🎮 Botni ishga tushirish"),
    BotCommand(command="oyinlar", description="🕹 O'yinlar ro'yxatini ko'rish"),
    BotCommand(command="reyting", description="🏆 Reyting va yuqori natijalar"),
]


# ── Registration ──────────────────────────────────────────────────────────────

async def register_commands(bot: Bot) -> None:
    """Register bot commands for all scopes. Safe to call on every startup."""
    errors: list[str] = []

    # 1. Default scope — public commands for every private chat / menu button
    try:
        await bot.set_my_commands(
            commands=_PUBLIC_COMMANDS,
            scope=BotCommandScopeDefault(),
        )
        logger.info(
            "Bot commands registered (Default): %s",
            [c.command for c in _PUBLIC_COMMANDS],
        )
    except Exception as exc:
        errors.append(f"Default scope: {exc}")
        logger.error("Failed to set Default commands: %s", exc)

    # 2. All group chats — so "/" shows commands in every group/supergroup
    try:
        await bot.set_my_commands(
            commands=_GROUP_COMMANDS,
            scope=BotCommandScopeAllGroupChats(),
        )
        logger.info(
            "Bot commands registered (AllGroupChats): %s",
            [c.command for c in _GROUP_COMMANDS],
        )
    except Exception as exc:
        errors.append(f"AllGroupChats scope: {exc}")
        logger.error("Failed to set AllGroupChats commands: %s", exc)

    # 3. Admin's private chat — full command list including admin tools
    if config.ADMIN_ID:
        try:
            await bot.set_my_commands(
                commands=_ADMIN_ALL_COMMANDS,
                scope=BotCommandScopeChat(chat_id=config.ADMIN_ID),
            )
            logger.info(
                "Bot commands registered (Admin chat %d): %s",
                config.ADMIN_ID,
                [c.command for c in _ADMIN_ALL_COMMANDS],
            )
        except Exception as exc:
            # Non-fatal: admin may not have started the bot yet
            errors.append(f"Admin chat scope: {exc}")
            logger.warning(
                "Could not set admin-scoped commands (admin may not have "
                "started the bot yet): %s", exc,
            )
    else:
        logger.warning(
            "ADMIN_ID not configured — skipping admin-scoped commands."
        )

    if errors:
        logger.warning("register_commands finished with %d error(s).", len(errors))
    else:
        logger.info("register_commands: all scopes registered successfully.")
