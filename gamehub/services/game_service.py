"""Business logic for sending game cards to Telegram users."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

from config import config

logger = logging.getLogger(__name__)

# Absolute path to webapp/ directory
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"


def _build_keyboard(
    game: dict,
    chat_id: int = 0,
) -> InlineKeyboardMarkup:
    """Build Telegram Mini App play button."""

    start_param = (
        f"{game['slug']}__{chat_id}"
        if chat_id
        else game["slug"]
    )

    url = (
        f"https://t.me/{config.BOT_USERNAME}/play"
        f"?startapp={start_param}"
    )

    button = InlineKeyboardButton(
        text="🎮 O'ynash",
        url=url,
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[[button]]
    )


def _build_caption(game: dict) -> str:
    """Build game card caption."""

    return (
        f"🎮 <b>{game['name']}</b>\n\n"
        f"{game['description']}"
    )


async def send_game_card(
    message: Message,
    game: dict,
) -> None:
    """
    Send a game card to Telegram.

    Supported local media:
        - MP4
        - GIF
        - JPG / JPEG
        - PNG
        - WEBP

    The game itself is opened as a Telegram Mini App
    through the 🎮 O'ynash button.
    """

    chat_id = message.chat.id

    keyboard = _build_keyboard(
        game,
        chat_id=chat_id,
    )

    caption = _build_caption(game)

    image_url: str = game.get(
        "image_url",
        "",
    )

    # ─────────────────────────────────────────────────────────────
    # Local media
    # ─────────────────────────────────────────────────────────────

    if image_url.startswith("/webapp/"):

        file_path = (
            WEBAPP_DIR
            / image_url.removeprefix("/webapp/")
        )

        if (
            file_path.exists()
            and file_path.is_file()
        ):
            try:
                suffix = file_path.suffix.lower()

                media = FSInputFile(
                    str(file_path)
                )

                # ─────────────────────────────────────────────
                # MP4 → Telegram video
                # ─────────────────────────────────────────────

                if suffix == ".mp4":

                    await message.answer_video(
                        video=media,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        supports_streaming=True,
                    )

                    return

                # ─────────────────────────────────────────────
                # GIF → Telegram animation
                # ─────────────────────────────────────────────

                if suffix == ".gif":

                    await message.answer_animation(
                        animation=media,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )

                    return

                # ─────────────────────────────────────────────
                # JPG / PNG / WEBP → Telegram photo
                # ─────────────────────────────────────────────

                if suffix in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                }:

                    await message.answer_photo(
                        photo=media,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                    )

                    return

                logger.warning(
                    "Unsupported local media extension: %s",
                    suffix,
                )

            except Exception as exc:

                logger.warning(
                    "Local media failed (%s), "
                    "falling back: %s",
                    file_path,
                    exc,
                )

        else:

            logger.warning(
                "Local media file not found: %s",
                file_path,
            )

    # ─────────────────────────────────────────────────────────────
    # Remote media
    # ─────────────────────────────────────────────────────────────

    if (
        image_url.startswith("http://")
        or image_url.startswith("https://")
    ):

        try:

            suffix = Path(
                image_url.split(
                    "?",
                    1,
                )[0]
            ).suffix.lower()

            # Remote MP4
            if suffix == ".mp4":

                await message.answer_video(
                    video=image_url,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    supports_streaming=True,
                )

                return

            # Remote GIF
            if suffix == ".gif":

                await message.answer_animation(
                    animation=image_url,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )

                return

            # Remote image
            await message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

            return

        except Exception as exc:

            logger.warning(
                "Remote media failed, "
                "falling back: %s",
                exc,
            )

    # ─────────────────────────────────────────────────────────────
    # Text fallback
    # ─────────────────────────────────────────────────────────────

    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )