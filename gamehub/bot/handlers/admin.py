"""Admin-only handler: /yangi — add a new game via FSM conversation."""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import config
from db.global_db import add_game

logger = logging.getLogger(__name__)
router = Router()


class AddGameFSM(StatesGroup):
    waiting_name = State()
    waiting_display = State()
    waiting_description = State()
    waiting_url_path = State()


def is_admin(message: Message) -> bool:
    return message.from_user.id == config.ADMIN_ID


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

@router.message(Command("yangi"))
async def cmd_yangi(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    await state.set_state(AddGameFSM.waiting_name)
    await message.answer(
        "🎮 <b>Yangi o'yin qo'shish</b>\n\n"
        "1️⃣ O'yinning <b>noyob identifikatori</b>ni kiriting (lotin, kichik harf, tire):\n"
        "<i>Masalan: chess, tetris, pacman</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )


@router.message(Command("bekor"), AddGameFSM.waiting_name)
@router.message(Command("bekor"), AddGameFSM.waiting_display)
@router.message(Command("bekor"), AddGameFSM.waiting_description)
@router.message(Command("bekor"), AddGameFSM.waiting_url_path)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Bekor qilindi.")


# ---------------------------------------------------------------------------
# Step 1 — name
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_name)
async def step_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip().lower()
    if not name.replace("-", "").replace("_", "").isalnum():
        await message.answer("⚠️ Faqat lotin harflar, raqamlar, tire yoki pastki chiziq kiriting.")
        return

    await state.update_data(name=name)
    await state.set_state(AddGameFSM.waiting_display)
    await message.answer(
        f"✅ ID: <code>{name}</code>\n\n"
        "2️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 2 — display name
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_display)
async def step_display(message: Message, state: FSMContext) -> None:
    display_name = message.text.strip()
    await state.update_data(display_name=display_name)
    await state.set_state(AddGameFSM.waiting_description)
    await message.answer(
        f"✅ Ko'rinadigan nomi: <b>{display_name}</b>\n\n"
        "3️⃣ Qisqa <b>ta'rif</b> kiriting:",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 3 — description
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_description)
async def step_description(message: Message, state: FSMContext) -> None:
    description = message.text.strip()
    await state.update_data(description=description)
    await state.set_state(AddGameFSM.waiting_url_path)
    await message.answer(
        "4️⃣ O'yinning <b>URL yo'li</b>ni kiriting:\n"
        "<i>Masalan: /webapp/games/chess.html</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 4 — url_path
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_url_path)
async def step_url_path(message: Message, state: FSMContext) -> None:
    url_path = message.text.strip()
    if not url_path.startswith("/"):
        await message.answer("⚠️ URL yo'li <code>/</code> bilan boshlanishi kerak.")
        return

    data = await state.get_data()
    await state.clear()

    try:
        game = await add_game(
            name=data["name"],
            display_name=data["display_name"],
            description=data["description"],
            url_path=url_path,
        )
        await message.answer(
            "✅ <b>O'yin muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🆔 ID: <code>{game['name']}</code>\n"
            f"📛 Nomi: <b>{game['display_name']}</b>\n"
            f"📝 Ta'rif: {game['description']}\n"
            f"🔗 URL: <code>{game['url_path']}</code>",
            parse_mode="HTML",
        )
        logger.info("Admin added game: %s", game["name"])
    except Exception as e:
        logger.exception("Failed to add game")
        await message.answer(f"❌ Xato yuz berdi: {e}")
