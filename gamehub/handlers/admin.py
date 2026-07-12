"""Admin-only handler: /yangi — upload a new game via 7-step FSM.

Steps
-----
1. Game name (display)
2. Slug (unique, URL-safe)
3. Description
4. Category
5. Upload HTML game file (.html document)
6. Upload thumbnail image (photo or image document)
7. Preview card → inline buttons: ✅ Saqlash | ✏️ Tahrirlash | ❌ Bekor
"""

import logging
from pathlib import Path

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    FSInputFile,
)

from config import config
from database.global_db import add_game, get_game_by_slug
from services.upload_service import save_html, save_image, ext_from_mime, image_db_url

logger = logging.getLogger(__name__)
router = Router()

# ── Allowed image MIME types ─────────────────────────────────────────────────
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}


# ── FSM States ───────────────────────────────────────────────────────────────

class AddGameFSM(StatesGroup):
    waiting_name        = State()   # 1 – display name
    waiting_slug        = State()   # 2 – unique slug
    waiting_description = State()   # 3 – description
    waiting_category    = State()   # 4 – category
    waiting_html        = State()   # 5 – HTML game file upload
    waiting_image       = State()   # 6 – thumbnail image upload
    waiting_confirm     = State()   # 7 – preview + save / edit / cancel


# ── Guards ───────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ── Keyboards ────────────────────────────────────────────────────────────────

def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Saqlash",      callback_data="admin:save"),
        InlineKeyboardButton(text="✏️ Tahrirlash",   callback_data="admin:edit"),
        InlineKeyboardButton(text="❌ Bekor",         callback_data="admin:cancel"),
    ]])


def _play_keyboard(slug: str) -> InlineKeyboardMarkup:
    url = f"{config.WEBAPP_URL.rstrip('/')}/games/{slug}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎮 O'ynash", web_app=WebAppInfo(url=url))
    ]])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _preview_caption(data: dict) -> str:
    return (
        f"🎮 <b>{data['name']}</b>\n\n"
        f"📝 {data['description']}\n\n"
        f"🗂 Kategoriya: <b>{data['category']}</b>\n"
        f"📄 HTML: <code>{data['slug']}.html</code>\n\n"
        "<i>Saqlashni tasdiqlaysizmi?</i>"
    )


async def _send_preview(message: Message, data: dict, bot: Bot) -> None:
    """Send the confirmation preview using the cached Telegram file_id."""
    caption  = _preview_caption(data)
    keyboard = _confirm_keyboard()
    image_id = data.get("image_file_id", "")

    if image_id:
        await message.answer_photo(
            photo=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await message.answer(caption, reply_markup=keyboard, parse_mode="HTML")


# ── /yangi entry ─────────────────────────────────────────────────────────────

@router.message(Command("yangi"))
async def cmd_yangi(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    await state.clear()
    await state.set_state(AddGameFSM.waiting_name)
    await message.answer(
        "🎮 <b>Yangi o'yin qo'shish</b>\n\n"
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )


# ── /bekor ───────────────────────────────────────────────────────────────────

@router.message(Command("bekor"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.")


# ── Step 1 – name ─────────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_name)
async def step_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Nom kamida 2 ta belgidan iborat bo'lishi kerak.")
        return

    await state.update_data(name=name)
    await state.set_state(AddGameFSM.waiting_slug)
    await message.answer(
        f"✅ Nomi: <b>{name}</b>\n\n"
        "2️⃣ <b>Slug</b> (noyob identifikator) kiriting:\n"
        "<i>Faqat kichik lotin harflar, raqamlar, tire (-) yoki pastki chiziq (_).</i>\n"
        "<i>Masalan: zombi, ilon-oyini, space-shooter</i>",
        parse_mode="HTML",
    )


# ── Step 2 – slug ─────────────────────────────────────────────────────────────

_SLUG_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")


@router.message(AddGameFSM.waiting_slug)
async def step_slug(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    slug = message.text.strip().lower()

    if not slug or not all(c in _SLUG_CHARS for c in slug):
        await message.answer(
            "⚠️ Slug faqat kichik lotin harflar, raqamlar, "
            "<code>-</code> yoki <code>_</code> dan iborat bo'lishi kerak.",
            parse_mode="HTML",
        )
        return

    # Uniqueness check
    existing = await get_game_by_slug(slug)
    if existing:
        await message.answer(
            f"⚠️ <code>{slug}</code> slugli o'yin allaqachon mavjud. "
            "Boshqa slug tanlang.",
            parse_mode="HTML",
        )
        return

    await state.update_data(slug=slug)
    await state.set_state(AddGameFSM.waiting_description)
    await message.answer(
        f"✅ Slug: <code>{slug}</code>\n\n"
        "3️⃣ O'yin haqida qisqa <b>ta'rif</b> kiriting:",
        parse_mode="HTML",
    )


# ── Step 3 – description ──────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_description)
async def step_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(AddGameFSM.waiting_category)
    await message.answer(
        "4️⃣ <b>Kategoriya</b>ni kiriting:\n"
        "<i>Masalan: arcade, puzzle, action, strategy, sport</i>",
        parse_mode="HTML",
    )


# ── Step 4 – category ─────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_category)
async def step_category(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    category = message.text.strip().lower()
    await state.update_data(category=category)
    await state.set_state(AddGameFSM.waiting_html)
    await message.answer(
        f"✅ Kategoriya: <b>{category}</b>\n\n"
        "5️⃣ O'yin <b>HTML faylini</b> yuboring:\n"
        "<i>Fayl <code>.html</code> kengaytmali bo'lishi kerak.</i>\n"
        "<i>Telegram orqali fayl (document) sifatida yuboring.</i>",
        parse_mode="HTML",
    )


# ── Step 5 – HTML file ────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_html)
async def step_html(message: Message, state: FSMContext) -> None:
    doc = message.document

    if not doc:
        await message.answer(
            "⚠️ Iltimos, HTML faylni <b>fayl (document)</b> sifatida yuboring.",
            parse_mode="HTML",
        )
        return

    filename = doc.file_name or ""
    if not filename.lower().endswith(".html"):
        await message.answer(
            "⚠️ Faqat <code>.html</code> kengaytmali fayl qabul qilinadi.",
            parse_mode="HTML",
        )
        return

    await state.update_data(html_file_id=doc.file_id, html_orig_name=filename)
    await state.set_state(AddGameFSM.waiting_image)
    await message.answer(
        f"✅ HTML fayl qabul qilindi: <code>{filename}</code>\n\n"
        "6️⃣ O'yin uchun <b>thumbnail rasm</b> yuboring:\n"
        "<i>Rasmni Telegram <b>foto</b> sifatida yoki rasm fayli (document) sifatida yuboring.</i>",
        parse_mode="HTML",
    )


# ── Step 6 – thumbnail image ──────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_image)
async def step_image(message: Message, state: FSMContext) -> None:
    file_id: str | None = None
    ext: str = ".jpg"

    if message.photo:
        # Compressed photo sent via Telegram camera/gallery
        file_id = message.photo[-1].file_id
        ext = ".jpg"

    elif message.document:
        doc = message.document
        mime = doc.mime_type or ""
        if mime not in ALLOWED_IMAGE_MIME:
            await message.answer(
                "⚠️ Faqat rasm fayllari qabul qilinadi (JPEG, PNG, GIF, WEBP).",
                parse_mode="HTML",
            )
            return
        file_id = doc.file_id
        # Try to get extension from original filename first
        orig = doc.file_name or ""
        suffix = Path(orig).suffix.lower()
        ext = suffix if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ext_from_mime(mime)
        if ext == ".jpeg":
            ext = ".jpg"

    else:
        await message.answer(
            "⚠️ Iltimos, rasmni <b>foto</b> yoki <b>rasm fayli</b> sifatida yuboring.",
            parse_mode="HTML",
        )
        return

    await state.update_data(image_file_id=file_id, image_ext=ext)
    await state.set_state(AddGameFSM.waiting_confirm)

    data = await state.get_data()
    await message.answer("✅ Rasm qabul qilindi! Tekshirib ko'ring 👇")
    await _send_preview(message, data, message.bot)


# ── Step 7 – Confirm callbacks ────────────────────────────────────────────────

@router.callback_query(F.data == "admin:save", AddGameFSM.waiting_confirm)
async def cb_save(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer("⏳ Saqlanmoqda...")

    data = await state.get_data()
    await state.clear()

    slug      = data["slug"]
    image_ext = data["image_ext"]

    try:
        # 1. Download and persist the HTML file
        await save_html(bot, data["html_file_id"], slug)

        # 2. Download and persist the thumbnail image
        await save_image(bot, data["image_file_id"], slug, image_ext)

        # 3. Insert into Global DB
        img_url  = image_db_url(slug, image_ext)
        html_file = f"{slug}.html"

        game = await add_game(
            slug=slug,
            name=data["name"],
            description=data["description"],
            html_file=html_file,
            category=data["category"],
            image_url=img_url,
            active=True,
        )

        # 4. Edit the preview message to remove the confirm buttons
        await callback.message.edit_reply_markup(reply_markup=None)

        # 5. Confirm to admin
        await callback.message.answer(
            "✅ <b>O'yin muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🆔 Slug: <code>{game['slug']}</code>\n"
            f"📛 Nomi: <b>{game['name']}</b>\n"
            f"📝 Ta'rif: {game['description']}\n"
            f"🗂 Kategoriya: {game['category']}\n"
            f"📄 HTML: <code>{game['html_file']}</code>\n"
            f"🖼 Rasm: <code>{game['image_url']}</code>\n\n"
            f"Hoziroq ko'rish: /oyinlar {game['slug']}",
            parse_mode="HTML",
        )

        # 6. Show the live game card (as users will see it)
        from services.game_service import send_game_card
        await send_game_card(callback.message, game)

        logger.info("Admin saved new game: slug=%s", slug)

    except Exception:
        logger.exception("Failed to save game slug=%s", slug)
        await callback.message.answer(
            "❌ Xato yuz berdi. Qayta urinib ko'ring: /yangi"
        )


@router.callback_query(F.data == "admin:edit", AddGameFSM.waiting_confirm)
async def cb_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("✏️ Qayta boshlash...")
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🔄 Jarayon qayta boshlandi.\n\n"
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )
    await state.set_state(AddGameFSM.waiting_name)


@router.callback_query(F.data == "admin:cancel", AddGameFSM.waiting_confirm)
async def cb_cancel_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("❌ Bekor qilindi.")
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ O'yin qo'shish bekor qilindi.")
