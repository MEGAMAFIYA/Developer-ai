"""Handler: /oyinlar — list all games or send a specific game card."""

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.global_db import get_all_games, get_game_by_slug
from services.game_service import send_game_card

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("oyinlar"))
async def cmd_oyinlar(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    slug = parts[1].strip().lower() if len(parts) > 1 else None

    if slug:
        await _send_single(message, slug)
    else:
        await _send_all(message)


async def _send_all(message: Message) -> None:
    games = await get_all_games(only_active=True)

    if not games:
        await message.answer("😔 Hozircha hech qanday o'yin mavjud emas.")
        return

    await message.answer(
        f"🎮 <b>Barcha o'yinlar ({len(games)} ta):</b>",
        parse_mode="HTML",
    )

    for game in games:
        try:
            await send_game_card(message, game)
        except Exception as e:
            logger.exception("Game card failed (%s): %s", game["slug"], e)

            await message.answer(
                f"🎮 <b>{game['name']}</b>\n\n{game['description']}",
                parse_mode="HTML",
            )

        await asyncio.sleep(0.3)


async def _send_single(message: Message, slug: str) -> None:
    game = await get_game_by_slug(slug)

    if not game:
        await message.answer(
            f"❌ <code>{slug}</code> nomli o'yin topilmadi.\n"
            "Barcha o'yinlar: /oyinlar",
            parse_mode="HTML",
        )
        return

    if not game["active"]:
        await message.answer("⚠️ Bu o'yin hozircha faol emas.")
        return

    await send_game_card(message, game)