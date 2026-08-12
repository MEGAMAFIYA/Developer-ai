"""Inline mode — search and launch games from the Telegram inline query."""

from pathlib import Path

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InlineQueryResultGif,
    InlineQueryResultMpeg4Gif,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.global_db import get_all_games
from config import config

router = Router()

# Media extensions that Telegram can play back as an "animation"
# (looping, sound-off video) inside an inline result.
_ANIMATION_EXTS = {".gif", ".mp4"}
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _resolve_media_url(image_url: str) -> str:
    """Turn a stored `image_url` (local `/webapp/...` path or absolute
    http(s) URL) into a public URL Telegram's servers can fetch.
    """

    image_url = (image_url or "").strip()

    if not image_url:
        return ""

    if image_url.startswith("/"):
        return f"{config.WEBAPP_URL.rstrip('/')}{image_url}"

    if image_url.startswith("http://") or image_url.startswith("https://"):
        return image_url

    return ""


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

        caption = f"🎮 <b>{name}</b>\n\n{description}"

        # ── Game media (photo / gif / mp4) ─────────────────────────────
        raw_image_url = str(game.get("image_url") or "").strip()
        media_url = _resolve_media_url(raw_image_url)
        suffix = Path(raw_image_url.split("?", 1)[0]).suffix.lower()

        result = None

        if media_url and suffix == ".gif":
            # GIF → InlineQueryResultGif. Selecting it sends the GIF
            # itself (with caption) as the message — no extra
            # input_message_content needed.
            result = InlineQueryResultGif(
                id=f"game:{slug}",
                gif_url=media_url,
                thumbnail_url=media_url,
                thumbnail_mime_type="image/gif",
                title=f"🎮 {name}",
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        elif media_url and suffix == ".mp4":
            # MP4 (used as a soundless "animation") → InlineQueryResultMpeg4Gif.
            result = InlineQueryResultMpeg4Gif(
                id=f"game:{slug}",
                mpeg4_url=media_url,
                thumbnail_url=media_url,
                thumbnail_mime_type="video/mp4",
                title=f"🎮 {name}",
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        elif media_url and (suffix in _PHOTO_EXTS or not suffix):
            # JPG / PNG / WEBP (or an unknown extension we still treat
            # as an image) → InlineQueryResultPhoto.
            result = InlineQueryResultPhoto(
                id=f"game:{slug}",
                photo_url=media_url,
                thumbnail_url=media_url,
                title=f"🎮 {name}",
                description=description[:200],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        if result is None:
            # No usable media → fall back to a plain text card, exactly
            # like before.
            result = InlineQueryResultArticle(
                id=f"game:{slug}",
                title=f"🎮 {name}",
                description=description[:200],
                input_message_content=InputTextMessageContent(
                    message_text=caption,
                    parse_mode="HTML",
                ),
                reply_markup=keyboard,
            )

        results.append(result)

    await inline_query.answer(
        results=results,
        cache_time=0,
        is_personal=True,
    )
