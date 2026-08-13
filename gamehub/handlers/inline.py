"""Inline mode — search and launch games from the Telegram inline query.

Picker (the "@Kichik_oyinlar_bot ..." results list) always uses
InlineQueryResultArticle so the list keeps its usual look — a small
thumbnail, bold title and description, exactly like before.

Telegram's article thumbnail must be a static JPEG; pointing it at a
`.gif`/`.mp4` file makes the preview silently disappear. So for
GIF/MP4 games we generate (and cache) a static poster frame with
ffmpeg via `services.poster_service` and use that as the thumbnail.

Article results can only carry *text* as their sent message — Telegram
does not allow photo/animation/video content for InlineQueryResultArticle.
So right after the user picks a game, we receive a `chosen_inline_result`
update (this requires "Inline feedback" to be enabled for the bot via
@BotFather → /setinlinefeedback → 100%) and immediately upgrade that
just-sent text message into the real photo/GIF/video with
`edit_message_media`, using the message's `inline_message_id`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, Router
from aiogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaAnimation,
    InputMediaPhoto,
    InputMediaVideo,
)

from database.global_db import get_all_games, get_game_by_slug
from config import config
from services.poster_service import get_or_create_poster

logger = logging.getLogger(__name__)

router = Router()

WEBAPP_DIR = Path(__file__).parent.parent / "webapp"

_ANIMATION_EXTS = {".gif", ".mp4"}
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _public_url(local_or_remote: str) -> str:
    """Turn a stored `image_url` (local `/webapp/...` path, or an
    absolute http(s) URL) into a public URL Telegram's servers can fetch.
    """

    local_or_remote = (local_or_remote or "").strip()

    if not local_or_remote:
        return ""

    if local_or_remote.startswith("/"):
        return f"{config.WEBAPP_URL.rstrip('/')}{local_or_remote}"

    if local_or_remote.startswith("http://") or local_or_remote.startswith("https://"):
        return local_or_remote

    return ""


def _build_keyboard(slug: str, user_id: int) -> InlineKeyboardMarkup:
    start_param = f"{slug}__{user_id}"
    url = f"https://t.me/{config.BOT_USERNAME}/play?startapp={start_param}"

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎮 O'ynash", url=url)]]
    )


def _build_caption(name: str, description: str) -> str:
    return f"🎮 <b>{name}</b>\n\n{description}"


async def _thumbnail_url_for(raw_image_url: str, suffix: str) -> str:
    """Resolve a *static* thumbnail URL suitable for an Article result.

    JPG/PNG/WEBP are used directly. GIF/MP4 assets get a cached poster
    frame generated via ffmpeg. Remote (http/https) GIF/MP4 assets are
    used as-is (best effort — we don't download+extract remote files).
    """

    if suffix in _PHOTO_EXTS or not raw_image_url:
        return _public_url(raw_image_url)

    if suffix in _ANIMATION_EXTS and raw_image_url.startswith("/webapp/"):
        source_path = WEBAPP_DIR / raw_image_url.removeprefix("/webapp/")
        poster = await get_or_create_poster(source_path)

        if poster is not None:
            rel = poster.relative_to(WEBAPP_DIR).as_posix()
            return _public_url(f"/webapp/{rel}")

        # Poster generation failed — no reliable static preview available.
        return ""

    # Remote gif/mp4 or anything else — best effort passthrough.
    return _public_url(raw_image_url)


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

        keyboard = _build_keyboard(slug, inline_query.from_user.id)
        caption = _build_caption(name, description)

        raw_image_url = str(game.get("image_url") or "").strip()
        suffix = Path(raw_image_url.split("?", 1)[0]).suffix.lower()

        thumbnail_url = await _thumbnail_url_for(raw_image_url, suffix)

        result_kwargs = {
            "id": f"game:{slug}",
            "title": f"🎮 {name}",
            "description": description[:200],
            "input_message_content": InputTextMessageContent(
                message_text=caption,
                parse_mode="HTML",
            ),
            "reply_markup": keyboard,
        }

        if thumbnail_url:
            result_kwargs["thumbnail_url"] = thumbnail_url
            result_kwargs["thumbnail_width"] = 320
            result_kwargs["thumbnail_height"] = 180

        results.append(InlineQueryResultArticle(**result_kwargs))

    await inline_query.answer(
        results=results,
        cache_time=0,
        is_personal=True,
    )


@router.chosen_inline_result()
async def on_game_chosen(chosen: ChosenInlineResult, bot: Bot) -> None:
    """Upgrade the just-sent text card into the real photo/GIF/video.

    Fires right after a user picks a game from the inline list. Requires
    "Inline feedback" to be enabled for the bot (@BotFather →
    /setinlinefeedback → 100%), otherwise `inline_message_id` never
    arrives and this handler has nothing to edit.
    """

    if not chosen.inline_message_id:
        return

    if not chosen.result_id.startswith("game:"):
        return

    slug = chosen.result_id.removeprefix("game:")

    game = await get_game_by_slug(slug)
    if not game:
        return

    name = str(game.get("name") or slug)
    description = str(game.get("description") or "")
    caption = _build_caption(name, description)
    keyboard = _build_keyboard(slug, chosen.from_user.id)

    raw_image_url = str(game.get("image_url") or "").strip()
    suffix = Path(raw_image_url.split("?", 1)[0]).suffix.lower()
    media_url = _public_url(raw_image_url)

    if not media_url:
        # No media to upgrade to — leave the text message as-is.
        return

    try:
        if suffix == ".gif":
            media = InputMediaAnimation(
                media=media_url,
                caption=caption,
                parse_mode="HTML",
            )
        elif suffix == ".mp4":
            media = InputMediaVideo(
                media=media_url,
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
            )
        elif suffix in _PHOTO_EXTS:
            media = InputMediaPhoto(
                media=media_url,
                caption=caption,
                parse_mode="HTML",
            )
        else:
            return

        await bot.edit_message_media(
            inline_message_id=chosen.inline_message_id,
            media=media,
            reply_markup=keyboard,
        )

    except Exception as exc:
        logger.warning(
            "[INLINE] Could not upgrade message media for %s: %s",
            slug,
            exc,
        )
