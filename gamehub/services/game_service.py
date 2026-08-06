"""Business logic for sending game cards to Telegram users."""

import logging
from pathlib import Path

from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    FSInputFile,
)

from config import config

logger = logging.getLogger(__name__)

# Absolute path to webapp/ directory (gamehub/webapp/)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"


def _build_keyboard(game: dict, chat_id: int = 0) -> InlineKeyboardMarkup:
    base = f"{config.WEBAPP_URL.rstrip('/')}/games/{game['slug']}"
    url = f"{base}?cid={chat_id}" if chat_id else base

    btn = InlineKeyboardButton(
        text="🎮 O'ynash",
        web_app=WebAppInfo(url=url)
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[[btn]]
    )


def _build_caption(game: dict) -> str:
    return (
        f"🎮 <b>{game['name']}</b>\n\n"
        f"{game['description']}"
    )


async def send_game_card(message: Message, game: dict) -> None:
    """Send one game as a Telegram photo (or text fallback) with Play button."""

    chat_id = (
        message.chat.id
        if message.chat.type in ("group", "supergroup")
        else 0
    )

    keyboard = _build_keyboard(game, chat_id=chat_id)
    caption = _build_caption(game)
    image_url: str = game.get("image_url", "")

    # Local image
    if image_url.startswith("/webapp/"):
        file_path = WEBAPP_DIR / image_url.removeprefix("/webapp/")
        if file_path.exists():
            try:
                await message.answer_photo(
                    photo=FSInputFile(str(file_path)),
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                return
            except Exception as exc:
                logger.warning(
                    "Local photo failed (%s), falling back: %s",
                    file_path,
                    exc,
                )

    # Remote image
    if image_url.startswith("http"):
        try:
            await message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except Exception as exc:
            logger.warning("Remote photo failed, falling back: %s", exc)

    # Text fallback
    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )