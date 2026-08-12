"""Inline mode — search and launch games from the Telegram inline query."""

from pathlib import Path

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.global_db import get_all_games
from config import config

router = Router()

# NOTE on why this uses InlineQueryResultArticle for everything:
#
# Telegram's InlineQueryResultGif / InlineQueryResultMpeg4Gif types do
# NOT support a "description" field (only "title"), and most Telegram
# clients render Photo/Gif/Mpeg4Gif inline results as bare thumbnail
# tiles with no visible text at all. That's why gif-covered games were
# showing up with just the raw gif and nothing else in the picker.
#
# InlineQueryResultArticle is the only result type that reliably shows
# thumbnail + bold title + grey description as a list row on every
# client (this is what produces the look in the screenshot). To still
# get the actual image/gif to appear in the *sent* message (together
# with the caption and the play button), we don't attach the media as
# a photo/gif result — instead the message text contains an invisible
# link to the media URL with `prefer_large_media`, which makes
# Telegram render it as a large inline preview above the text.
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_ANIMATION_EXTS = {".gif", ".mp4"}


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
        has_media = bool(media_url) and (suffix in _PHOTO_EXTS or suffix in _ANIMATION_EXTS or not suffix)

        if has_media:
            # Zero-width link at the very start of the message: it isn't
            # visible to the user, but its `href` is what Telegram uses
            # to build the large media preview above the text.
            message_text = f'<a href="{media_url}">&#8203;</a>{caption}'
            link_preview = LinkPreviewOptions(
                url=media_url,
                prefer_large_media=True,
                show_above_text=True,
            )
        else:
            message_text = caption
            link_preview = None

        # InlineQueryResultArticle is used for every game (regardless of
        # media type) so the picker always shows thumbnail + title +
        # description consistently — see note above.
        result = InlineQueryResultArticle(
            id=f"game:{slug}",
            title=f"🎮 {name}",
            description=description[:200],
            thumbnail_url=media_url or None,
            input_message_content=InputTextMessageContent(
                message_text=message_text,
                parse_mode="HTML",
                link_preview_options=link_preview,
            ),
            reply_markup=keyboard,
        )

        results.append(result)

    await inline_query.answer(
        results=results,
        cache_time=0,
        is_personal=True,
    )
