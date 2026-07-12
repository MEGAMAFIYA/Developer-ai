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


def _build_keyboard(game: dict, in_group: bool = False) -> InlineKeyboardMarkup:
    url = f"{config.WEBAPP_URL.rstrip('/')}/games/{game['slug']}"
    # Telegram only allows web_app inline buttons in private chats.
    # In groups/channels we fall back to a plain URL button.
    btn = (
        InlineKeyboardButton(text="🎮 O'ynash", url=url)
        if in_group
        else InlineKeyboardButton(text="🎮 O'ynash", web_app=WebAppInfo(url=url))
    )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def _build_caption(game: dict) -> str:
    return (
        f"🎮 <b>{game['name']}</b>\n\n"
        f"{game['description']}"
    )


async def send_game_card(message: Message, game: dict) -> None:
    """Send one game as a Telegram photo (or text fallback) with Play button."""
    in_group = message.chat.type in ("group", "supergroup", "channel")
    keyboard = _build_keyboard(game, in_group=in_group)
    caption  = _build_caption(game)
    image_url: str = game.get("image_url", "")

    # 1) Local file stored under webapp/assets/games/
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
                logger.warning("Local photo failed (%s), falling back: %s", file_path, exc)

    # 2) Remote URL
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

    # 3) Text fallback
    await message.answer(caption, reply_markup=keyboard, parse_mode="HTML")
