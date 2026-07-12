"""Admin-only handler: /yangi — add a new game (6-step FSM)."""

import logging
from pathlib import Path

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import config
from database.global_db import add_game
from services.game_service import send_game_card

logger = logging.getLogger(__name__)
router = Router()

# Folder where uploaded game images are stored
ASSETS_DIR = Path(__file__).parent.parent / "webapp" / "assets" / "games"


class AddGameFSM(StatesGroup):
    waiting_name        = State()   # Step 1 – display name
    waiting_slug        = State()   # Step 2 – unique slug
    waiting_description = State()   # Step 3 – description
    waiting_category    = State()   # Step 4 – category
    waiting_image       = State()   # Step 5 – photo upload
    waiting_html_file   = State()   # Step 6 – HTML filename


def _is_admin(message: Message) -> bool:
    return message.from_user.id == config.ADMIN_ID


# ---------------------------------------------------------------------------
# /yangi entry
# ---------------------------------------------------------------------------

@router.message(Command("yangi"))
async def cmd_yangi(message: Message, state: FSMContext) -> None:
    if not _is_admin(message):
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    await state.set_state(AddGameFSM.waiting_name)
    await message.answer(
        "🎮 <b>Yangi o'yin qo'shish</b>\n\n"
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# /bekor — cancel from any step
# ---------------------------------------------------------------------------

@router.message(Command("bekor"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        return
    await state.clear()
    await message.answer("❌ Bekor qilindi.")


# ---------------------------------------------------------------------------
# Step 1 – name
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_name)
async def step_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Nom kamida 2 ta belgidan iborat bo'lishi kerak.")
        return

    await state.update_data(name=name)
    await state.set_state(AddGameFSM.waiting_slug)
    await message.answer(
        f"✅ Nomi: <b>{name}</b>\n\n"
        "2️⃣ O'yinning <b>noyob identifikatori</b>ni kiriting (slug):\n"
        "<i>Faqat kichik lotin harflar, raqamlar, tire. Masalan: ilon-oyini</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 2 – slug
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_slug)
async def step_slug(message: Message, state: FSMContext) -> None:
    slug = message.text.strip().lower()
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not slug or not all(c in allowed for c in slug):
        await message.answer(
            "⚠️ Slug faqat kichik lotin harflar, raqamlar, tire (-) yoki pastki chiziq (_) "
            "dan iborat bo'lishi kerak."
        )
        return

    await state.update_data(slug=slug)
    await state.set_state(AddGameFSM.waiting_description)
    await message.answer(
        f"✅ Slug: <code>{slug}</code>\n\n"
        "3️⃣ O'yin haqida qisqa <b>ta'rif</b> kiriting:",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 3 – description
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_description)
async def step_description(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AddGameFSM.waiting_category)
    await message.answer(
        "4️⃣ <b>Kategoriya</b>ni kiriting:\n"
        "<i>Masalan: arcade, puzzle, action, strategy, sport</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 4 – category
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_category)
async def step_category(message: Message, state: FSMContext) -> None:
    category = message.text.strip().lower()
    await state.update_data(category=category)
    await state.set_state(AddGameFSM.waiting_image)
    await message.answer(
        f"✅ Kategoriya: <b>{category}</b>\n\n"
        "5️⃣ O'yin uchun <b>rasm</b> yuboring (foto):\n"
        "<i>Rasmni Telegram foto sifatida yuboring.</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 5 – image upload
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_image)
async def step_image(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer("⚠️ Iltimos, rasmni <b>foto</b> sifatida yuboring.")
        return

    data = await state.get_data()
    slug = data["slug"]

    # Download the largest photo variant
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    local_path = ASSETS_DIR / f"{slug}.jpg"

    await bot.download_file(file_info.file_path, destination=str(local_path))

    image_url = f"/webapp/assets/games/{slug}.jpg"
    await state.update_data(image_url=image_url)
    await state.set_state(AddGameFSM.waiting_html_file)

    await message.answer(
        "✅ Rasm saqlandi!\n\n"
        "6️⃣ <b>HTML fayl nomini</b> kiriting:\n"
        "<i>Masalan: zombi.html</i>\n"
        "<i>Fayl <code>webapp/games/</code> papkasida mavjud bo'lishi kerak.</i>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Step 6 – html_file → save to DB
# ---------------------------------------------------------------------------

@router.message(AddGameFSM.waiting_html_file)
async def step_html_file(message: Message, state: FSMContext) -> None:
    html_file = message.text.strip()
    if not html_file.endswith(".html"):
        await message.answer("⚠️ Fayl nomi <code>.html</code> bilan tugashi kerak.")
        return

    data = await state.get_data()
    await state.clear()

    try:
        game = await add_game(
            slug=data["slug"],
            name=data["name"],
            description=data["description"],
            html_file=html_file,
            category=data["category"],
            image_url=data.get("image_url", ""),
        )
        await message.answer(
            "✅ <b>O'yin muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🆔 Slug: <code>{game['slug']}</code>\n"
            f"📛 Nomi: <b>{game['name']}</b>\n"
            f"📝 Ta'rif: {game['description']}\n"
            f"🗂 Kategoriya: {game['category']}\n"
            f"📄 HTML: <code>{game['html_file']}</code>\n\n"
            f"Ko'rish uchun: /oyinlar {game['slug']}",
            parse_mode="HTML",
        )
        logger.info("Admin added game: %s", game["slug"])

        # Preview the card immediately
        await send_game_card(message, game)

    except Exception as exc:
        logger.exception("Failed to save game")
        await message.answer(f"❌ Xato yuz berdi: {exc}")
