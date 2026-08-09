"""Inline mode — search and launch games from the Telegram inline query."""

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.global_db import get_all_games
from config import config

router = Router()


@router.inline_query()
async def inline_games(inline_query: InlineQuery) -> None:
    query = (inline_query.query or "").strip().lower()

    games = await get_all_games(only_active=True)

    # Query bo'sh bo'lsa barcha faol o'yinlarni ko'rsatamiz.
    # Yozilgan matn bo'lsa nom, slug va description bo'yicha qidiramiz.
    if query:
        games = [
            game
            for game in games
            if query in str(game.get("name", "")).lower()
            or query in str(game.get("slug", "")).lower()
            or query in str(game.get("description", "")).lower()
        ]

    results = []

    for game in games[:50]:
        slug = str(game["slug"])
        name = str(game.get("name") or slug)
        description = str(game.get("description") or "")

        start_param = f"{slug}__{inline_query.from_user.id}"
        url = (
            f"https://t.me/{config.BOT_USERNAME}/play"
            f"?startapp={start_param}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎮 O'ynash",
                        url=url,
                    )
                ]
            ]
        )

        # ── Game image / thumbnail ────────────────────────────────────────
        image_url = str(game.get("image_url") or "").strip()

        if image_url.startswith("/"):
            thumbnail_url = (
                f"{config.WEBAPP_URL.rstrip('/')}"
                f"{image_url}"
            )
        elif image_url.startswith("http://") or image_url.startswith("https://"):
            thumbnail_url = image_url
        else:
            thumbnail_url = ""

        result_kwargs = {
            "id": f"game:{slug}",
            "title": f"🎮 {name}",
            "description": description[:200],
            "input_message_content": InputTextMessageContent(
                message_text=(
                    f"🎮 <b>{name}</b>\n\n"
                    f"{description}"
                ),
                parse_mode="HTML",
            ),
            "reply_markup": keyboard,
        }

        # Rasm mavjud bo'lsa Telegram inline natijasiga thumbnail beradi.
        if thumbnail_url:
            result_kwargs["thumbnail_url"] = thumbnail_url
            result_kwargs["thumbnail_width"] = 320
            result_kwargs["thumbnail_height"] = 180

        results.append(
            InlineQueryResultArticle(**result_kwargs)
        )

    await inline_query.answer(
        results=results,
        cache_time=0,
        is_personal=True,
    )