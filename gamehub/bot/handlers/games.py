"""Handler: /oyinlar — list games or launch a game WebApp."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from config import config
from db.global_db import get_all_games, get_game_by_name

router = Router()


@router.message(Command("oyinlar"))
async def cmd_oyinlar(message: Message) -> None:
    # Parse optional game name argument
    parts = message.text.split(maxsplit=1)
    game_name = parts[1].strip().lower() if len(parts) > 1 else None

    if game_name:
        await _send_game(message, game_name)
    else:
        await _list_games(message)


async def _list_games(message: Message) -> None:
    games = await get_all_games()

    if not games:
        await message.answer("😔 Hozircha hech qanday o'yin mavjud emas.")
        return

    lines = ["🎮 <b>Mavjud o'yinlar:</b>\n"]
    for g in games:
        lines.append(f"• <b>{g['display_name']}</b> — /oyinlar {g['name']}")
        if g["description"]:
            lines.append(f"  <i>{g['description']}</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _send_game(message: Message, game_name: str) -> None:
    game = await get_game_by_name(game_name)

    if not game:
        await message.answer(
            f"❌ <code>{game_name}</code> nomli o'yin topilmadi.\n"
            "Barcha o'yinlar: /oyinlar",
            parse_mode="HTML",
        )
        return

    webapp_url = f"{config.WEBAPP_URL.rstrip('/')}{game['url_path']}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🎮 O'ynash",
            web_app=WebAppInfo(url=webapp_url),
        )
    ]])

    await message.answer(
        f"🕹 <b>{game['display_name']}</b>\n\n"
        f"{game['description']}\n\n"
        "Pastdagi tugmani bosib o'yinni boshlang! 👇",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
