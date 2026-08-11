"""Admin-only /yangi handler.

Yangi o'yin qo'shish:

1. Nomi
2. Slug
3. Description
4. Category
5. HTML fayl
6. Thumbnail:
   - 🎬 MP4 YARATISH
   - yoki rasm/GIF
7. Preview
8. Saqlash

MP4 rejimi:
- HTML o'yin tayyorlanadi
- Admin ▶️ BOSHLASH tugmasini bosadi
- O'yin ochiladi
- Admin o'yinni o'zi o'ynaydi
- 🎥 Yozishni boshlash/to'xtatish boshqaruvi
- WEBM → 640x360 MP4
- MP4 preview sifatida ko'rsatiladi
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import config
from database.global_db import add_game, get_game_by_slug
from services.upload_service import (
    image_ext_from_filename_or_mime,
    image_db_url,
    save_html_bytes,
    save_image_bytes,
)

logger = logging.getLogger(__name__)

router = Router()

WEBAPP_DIR = (
    Path(__file__).resolve().parent.parent
    / "webapp"
)


# ============================================================
# FSM
# ============================================================

class AddGameFSM(StatesGroup):
    waiting_name = State()
    waiting_slug = State()
    waiting_description = State()
    waiting_category = State()
    waiting_html = State()
    waiting_image = State()
    waiting_recording_start = State()
    waiting_recording = State()
    waiting_confirm = State()


# ============================================================
# ADMIN
# ============================================================

def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ============================================================
# THUMBNAIL KEYBOARD
# ============================================================

def _thumbnail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 MP4 YARATISH",
                    callback_data="admin:create_mp4",
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Rasm/GIF yuborish",
                    callback_data="admin:thumbnail_info",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )


# ============================================================
# RECORDING START KEYBOARD
# ============================================================

def _recording_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ BOSHLASH",
                    callback_data="admin:recording_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )


# ============================================================
# RECORDING CONTROL KEYBOARD
# ============================================================

def _recording_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎥 YOZISH",
                    callback_data="admin:recording_toggle",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏹ TO'XTATISH",
                    callback_data="admin:recording_stop",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )


# ============================================================
# CONFIRM KEYBOARD
# ============================================================

def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Saqlash",
                    callback_data="admin:save",
                ),
                InlineKeyboardButton(
                    text="✏️ Tahrirlash",
                    callback_data="admin:edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )


# ============================================================
# PREVIEW CAPTION
# ============================================================

def _preview_caption(data: dict) -> str:
    media_kind = data.get(
        "image_kind",
        "photo",
    )

    if media_kind == "mp4":
        media_text = "🎬 MP4 yozib olindi"
    elif media_kind in {
        "animation",
        "gif_document",
    }:
        media_text = "🎞 GIF yuklandi"
    else:
        media_text = "🖼 Thumbnail yuklandi"

    return (
        f"🎮 <b>{data['name']}</b>\n\n"
        f"📝 {data['description']}\n\n"
        f"🗂 Kategoriya: "
        f"<b>{data['category']}</b>\n"
        f"📄 HTML: "
        f"<code>{data['slug']}.html</code>\n"
        f"{media_text}\n\n"
        "<i>Saqlashni tasdiqlaysizmi?</i>"
    )


# ============================================================
# TELEGRAM FILE DOWNLOADER
# ============================================================

async def _download_telegram_bytes(
    bot: Bot,
    file_id: str,
) -> bytes:
    """Telegram faylini xotiraga yuklaydi."""

    buffer = io.BytesIO()

    file_info = await bot.get_file(
        file_id
    )

    await bot.download_file(
        file_info.file_path,
        destination=buffer,
    )

    return buffer.getvalue()

# ============================================================
# /YANGI
# ============================================================

@router.message(Command("yangi"))
async def cmd_yangi(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.from_user:
        return

    if not _is_admin(
        message.from_user.id
    ):
        await message.answer(
            "⛔ Bu buyruq faqat admin uchun!"
        )
        return

    await state.clear()

    await state.set_state(
        AddGameFSM.waiting_name
    )

    await message.answer(
        "🎮 <b>Yangi o'yin qo'shish</b>\n\n"
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni "
        "kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )


# ============================================================
# /BEKOR
# ============================================================

@router.message(Command("bekor"))
async def cmd_cancel(
    message: Message,
    state: FSMContext,
) -> None:

    current_state = await state.get_state()

    if current_state is None:
        return

    await state.clear()

    await message.answer(
        "❌ Jarayon bekor qilindi."
    )


# ============================================================
# STEP 1 — NAME
# ============================================================

@router.message(AddGameFSM.waiting_name)
async def step_name(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn kiriting."
        )
        return

    name = message.text.strip()

    if len(name) < 2:
        await message.answer(
            "⚠️ Nom kamida 2 ta belgidan "
            "iborat bo'lishi kerak."
        )
        return

    await state.update_data(
        name=name
    )

    await state.set_state(
        AddGameFSM.waiting_slug
    )

    await message.answer(
        f"✅ Nomi: <b>{name}</b>\n\n"
        "2️⃣ <b>Slug</b> kiriting:\n"
        "<i>Faqat kichik lotin harflari, "
        "raqamlar, - yoki _.</i>\n\n"
        "<i>Masalan: zombi, ilon-oyini</i>",
        parse_mode="HTML",
    )


# ============================================================
# SLUG CHARACTERS
# ============================================================

_SLUG_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_"
)


# ============================================================
# STEP 2 — SLUG
# ============================================================

@router.message(AddGameFSM.waiting_slug)
async def step_slug(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn kiriting."
        )
        return

    slug = (
        message.text
        .strip()
        .lower()
    )

    if (
        not slug
        or not all(
            char in _SLUG_CHARS
            for char in slug
        )
    ):
        await message.answer(
            "⚠️ Slug faqat kichik lotin "
            "harflari, raqamlar, "
            "<code>-</code> yoki "
            "<code>_</code> dan iborat.",
            parse_mode="HTML",
        )
        return

    existing = await get_game_by_slug(
        slug
    )

    if existing:
        await message.answer(
            f"⚠️ <code>{slug}</code> "
            "slugli o'yin allaqachon mavjud.",
            parse_mode="HTML",
        )
        return

    await state.update_data(
        slug=slug
    )

    await state.set_state(
        AddGameFSM.waiting_description
    )

    await message.answer(
        f"✅ Slug: <code>{slug}</code>\n\n"
        "3️⃣ O'yin haqida qisqa "
        "<b>ta'rif</b> kiriting:",
        parse_mode="HTML",
    )


# ============================================================
# STEP 3 — DESCRIPTION
# ============================================================

@router.message(
    AddGameFSM.waiting_description
)
async def step_description(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn kiriting."
        )
        return

    description = (
        message.text.strip()
    )

    if not description:
        await message.answer(
            "⚠️ Ta'rif bo'sh bo'lishi mumkin emas."
        )
        return

    await state.update_data(
        description=description
    )

    await state.set_state(
        AddGameFSM.waiting_category
    )

    await message.answer(
        "4️⃣ <b>Kategoriya</b>ni kiriting:\n"
        "<i>arcade, puzzle, action, "
        "strategy, sport...</i>",
        parse_mode="HTML",
    )


# ============================================================
# STEP 4 — CATEGORY
# ============================================================

@router.message(
    AddGameFSM.waiting_category
)
async def step_category(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn kiriting."
        )
        return

    category = (
        message.text
        .strip()
        .lower()
    )

    if not category:
        await message.answer(
            "⚠️ Kategoriya bo'sh bo'lishi mumkin emas."
        )
        return

    await state.update_data(
        category=category
    )

    await state.set_state(
        AddGameFSM.waiting_html
    )

    await message.answer(
        f"✅ Kategoriya: "
        f"<b>{category}</b>\n\n"
        "5️⃣ O'yinning <b>HTML faylini</b> "
        "document sifatida yuboring.\n\n"
        "📄 Faqat <code>.html</code> fayl.",
        parse_mode="HTML",
    )


# ============================================================
# STEP 5 — HTML
# ============================================================

@router.message(
    AddGameFSM.waiting_html
)
async def step_html(
    message: Message,
    state: FSMContext,
) -> None:

    document = message.document

    if not document:
        await message.answer(
            "⚠️ HTML faylni "
            "<b>document</b> sifatida yuboring.",
            parse_mode="HTML",
        )
        return

    filename = (
        document.file_name
        or ""
    )

    if not filename.lower().endswith(
        ".html"
    ):
        await message.answer(
            "⚠️ Faqat <code>.html</code> "
            "fayl qabul qilinadi.",
            parse_mode="HTML",
        )
        return

    await state.update_data(
        html_file_id=document.file_id,
        html_orig_name=filename,
    )

    await state.set_state(
        AddGameFSM.waiting_image
    )

    await message.answer(
        f"✅ HTML qabul qilindi: "
        f"<code>{filename}</code>\n\n"
        "6️⃣ <b>Thumbnail</b> tanlang:\n\n"
        "🎬 <b>MP4 YARATISH</b> — "
        "o'yinni qo'lda o'ynab, "
        "ekran yozuvini MP4 qilamiz.\n\n"
        "Yoki quyidagi tugmani bosmasdan "
        "🖼 rasm / 🎞 GIF yuborishingiz mumkin.",
        reply_markup=_thumbnail_keyboard(),
        parse_mode="HTML",
    )

# ============================================================
# STEP 6 — THUMBNAIL / RASM / GIF
# ============================================================

@router.message(
    AddGameFSM.waiting_image
)
async def step_image(
    message: Message,
    state: FSMContext,
) -> None:
    """
    Thumbnail bosqichi.

    Admin:
      • rasm yuborishi mumkin
      • GIF yuborishi mumkin
      • yoki 🎬 MP4 YARATISH tugmasini bosishi mumkin
    """

    file_id: str | None = None
    ext = ".jpg"
    image_kind = "photo"

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    if message.photo:
        file_id = message.photo[-1].file_id
        ext = ".jpg"
        image_kind = "photo"

    # --------------------------------------------------------
    # TELEGRAM ANIMATION
    # --------------------------------------------------------

    elif message.animation:
        file_id = message.animation.file_id
        ext = ".gif"
        image_kind = "animation"

    # --------------------------------------------------------
    # DOCUMENT
    # --------------------------------------------------------

    elif message.document:

        document = message.document

        ext = image_ext_from_filename_or_mime(
            document.file_name,
            document.mime_type,
        )

        if ext is None:
            await message.answer(
                "⚠️ Faqat rasm fayllari qabul qilinadi:\n\n"
                "🖼 JPEG\n"
                "🖼 PNG\n"
                "🎞 GIF\n"
                "🖼 WEBP",
                parse_mode="HTML",
            )
            return

        file_id = document.file_id

        if ext.lower() == ".gif":
            image_kind = "gif_document"
        else:
            image_kind = "document"

    # --------------------------------------------------------
    # NOTHING
    # --------------------------------------------------------

    else:
        await message.answer(
            "⚠️ Rasm yoki GIF yuboring.\n\n"
            "Yoki quyidagi tugma orqali "
            "🎬 MP4 yaratishingiz mumkin.",
            reply_markup=_thumbnail_keyboard(),
        )
        return

    # --------------------------------------------------------
    # SAVE MEDIA INFORMATION TO FSM
    # --------------------------------------------------------

    await state.update_data(
        image_file_id=file_id,
        image_ext=ext,
        image_kind=image_kind,
        image_path=None,
    )

    await state.set_state(
        AddGameFSM.waiting_confirm
    )

    data = await state.get_data()

    await message.answer(
        "✅ Thumbnail qabul qilindi!\n\n"
        "Tekshirib ko'ring 👇"
    )

    await _send_preview(
        message,
        data,
    )


# ============================================================
# PREVIEW
# ============================================================

async def _send_preview(
    message: Message,
    data: dict,
) -> None:
    """
    Yangi o'yin preview kartasini yuboradi.
    """

    caption = _preview_caption(
        data
    )

    keyboard = _confirm_keyboard()

    image_id = data.get(
        "image_file_id"
    )

    image_kind = data.get(
        "image_kind"
    )

    # --------------------------------------------------------
    # MP4
    # --------------------------------------------------------

    if (
        image_id
        and image_kind == "mp4"
    ):
        await message.answer_video(
            video=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
            supports_streaming=True,
        )
        return

    # --------------------------------------------------------
    # TELEGRAM GIF
    # --------------------------------------------------------

    if (
        image_id
        and image_kind == "animation"
    ):
        await message.answer_animation(
            animation=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # GIF DOCUMENT
    # --------------------------------------------------------

    if (
        image_id
        and image_kind == "gif_document"
    ):
        await message.answer_document(
            document=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # NORMAL IMAGE
    # --------------------------------------------------------

    if image_id:
        await message.answer_photo(
            photo=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # TEXT ONLY
    # --------------------------------------------------------

    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# MP4 CREATION — START SCREEN
# ============================================================

@router.callback_query(
    F.data == "admin:create_mp4",
    AddGameFSM.waiting_image,
)
async def cb_create_mp4(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    MP4 rejimini boshlaydi.

    Bu callback hali recordingni boshlamaydi.

    Avval admin:
        🎬 MP4 YARATISH
    ni bosadi.

    Keyin:
        ▶️ BOSHLASH
    chiqadi.

    Admin BOSHLASHni bosgandan keyingina
    o'yin oynasi tayyorlanadi.
    """

    await callback.answer()

    data = await state.get_data()

    if not data.get("html_file_id"):
        await callback.message.answer(
            "❌ HTML fayl topilmadi.\n\n"
            "Iltimos, /yangi jarayonini qaytadan boshlang."
        )
        return

    await state.set_state(
        AddGameFSM.waiting_recording_start
    )

    await callback.message.answer(
        "🎬 <b>MP4 yaratish rejimi</b>\n\n"
        "O'yin hali boshlanmadi.\n\n"
        "Keyingi bosqichda o'yin "
        "<b>640×360</b> yozuv oynasida tayyorlanadi.\n\n"
        "▶️ <b>BOSHLASH</b> tugmasini bossangiz, "
        "o'yinga kirasiz va uni o'zingiz o'ynaysiz.\n\n"
        "🎥 Yozishni esa o'yin ichidagi "
        "tugma orqali xohlagan vaqtingizda "
        "boshlashingiz mumkin.",
        reply_markup=_recording_start_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# THUMBNAIL INFORMATION
# ============================================================

@router.callback_query(
    F.data == "admin:thumbnail_info",
    AddGameFSM.waiting_image,
)
async def cb_thumbnail_info(
    callback: CallbackQuery,
) -> None:

    await callback.answer()

    await callback.message.answer(
        "🖼 <b>Thumbnail tanlash</b>\n\n"
        "Sizda 2 ta imkoniyat bor:\n\n"
        "🎬 <b>MP4 YARATISH</b>\n"
        "O'yinni o'zingiz o'ynaysiz va "
        "kerakli qismini yozib olasiz.\n\n"
        "🖼 <b>Rasm/GIF</b>\n"
        "Tayyor rasm yoki GIF yuborishingiz mumkin.\n\n"
        "MP4 rejimida yozish faqat "
        "siz 🎥 YOZISH tugmasini bosganingizda "
        "boshlanadi.",
        reply_markup=_thumbnail_keyboard(),
        parse_mode="HTML",
    )