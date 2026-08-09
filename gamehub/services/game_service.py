"""Business logic for sending game cards to Telegram users."""

import logging
from pathlib import Path

from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import config

logger = logging.getLogger(__name__)

# Absolute path to webapp/ directory (gamehub/webapp/)
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"


def _build_keyboard(game: dict, chat_id: int = 0) -> InlineKeyboardMarkup:
    # Direct Mini App link registered via BotFather.
    # The start_param contains the game slug and chat ID.
    start_param = (
        f"{game['slug']}__{chat_id}"
        if chat_id
        else game['slug']
    )

    url = (
        f"https://t.me/{config.BOT_USERNAME}/play"
        f"?startapp={start_param}"
    )

    btn = InlineKeyboardButton(
        text="🎮 O'ynash",
        url=url,
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
    """Send one game as a Telegram photo/animation with Play button."""

    chat_id = message.chat.id

    keyboard = _build_keyboard(game, chat_id=chat_id)
    caption = _build_caption(game)
    image_url: str = game.get("image_url", "")

    # Local image/animation
    if image_url.startswith("/webapp/"):
        file_path = WEBAPP_DIR / image_url.removeprefix("/webapp/")

        if file_path.exists():
            try:
                suffix = file_path.suffix.lower()

                # GIF → Telegram animation
                if suffix == ".gif":
                    await message.answer_animation(
                        animation=str(file_path),
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )
                    return

                # Normal image → Telegram photo
                await message.answer_photo(
                    photo=str(file_path),
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                return

            except Exception as exc:
                logger.warning(
                    "Local media failed (%s), falling back: %s",
                    file_path,
                    exc,
                )

    # Remote image
    if image_url.startswith("http"):
        try:
            suffix = Path(image_url.split("?", 1)[0]).suffix.lower()

            # Remote GIF → Telegram animation
            if suffix == ".gif":
                await message.answer_animation(
                    animation=image_url,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                return

            # Remote normal image → Telegram photo
            await message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        except Exception as exc:
            logger.warning(
                "Remote media failed, falling back: %s",
                exc,
            )

    # Text fallback
    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )