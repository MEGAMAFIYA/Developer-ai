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
- HTML o'yin brauzerda ochiladi
- Admin o'yinni o'zi o'ynaydi
- 🎥 yozishni boshlaydi
- ⏹ yozishni to'xtatadi
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
from database.global_db import (
    add_game,
    get_game_by_slug,
)
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

    # Thumbnail
    waiting_image = State()

    # MP4 recording
    waiting_recording_start = State()
    waiting_recording = State()

    # Final preview / save
    waiting_confirm = State()

# ============================================================
# ADMIN
# ============================================================

def _is_admin(user_id: int) -> bool:
    """
    Faqat config.ADMIN_ID ga ega foydalanuvchiga
    /yangi va MP4 recording funksiyalaridan foydalanishga
    ruxsat beradi.
    """

    return user_id == config.ADMIN_ID


# ============================================================
# THUMBNAIL KEYBOARD
# ============================================================

def _thumbnail_keyboard() -> InlineKeyboardMarkup:
    """
    Thumbnail tanlash oynasi.
    """

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
    """
    MP4 rejimiga kirgandan keyingi boshlash oynasi.
    """

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

def _recording_keyboard(
    recording: bool = False,
) -> InlineKeyboardMarkup:
    """
    Recording vaqtida ko'rsatiladigan boshqaruv.

    recording=False:
        🎥 YOZISH

    recording=True:
        ⏹ TO'XTATISH
    """

    if recording:
        return InlineKeyboardMarkup(
            inline_keyboard=[
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
    """
    Tayyor previewdan keyin:
    - Saqlash
    - Tahrirlash
    - Bekor qilish
    """

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
    """
    Yangi o'yin preview kartasi uchun caption.
    """

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
    """
    Telegram faylini xotiraga yuklaydi.
    """

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
# PREVIEW
# ============================================================

async def _send_preview(
    message: Message,
    data: dict,
) -> None:
    """
    Yangi o'yin preview kartasini yuboradi.

    MP4 / GIF / rasm formatlarini alohida
    ko'rsatadi.
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

@router.message(
    AddGameFSM.waiting_name
)
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

@router.message(
    AddGameFSM.waiting_slug
)
async def step_slug(
    message: Message,
    state: FSMContext
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
        "o'yinni brauzerda ochib, "
        "o'zingiz o'ynab video yozishingiz mumkin.\n\n"
        "Yoki 🖼 rasm / 🎞 GIF yuborishingiz mumkin.",
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
    Admin rasm yoki GIF yuborsa,
    uni thumbnail sifatida qabul qiladi.

    MP4 uchun esa yuqoridagi
    🎬 MP4 YARATISH tugmasi ishlatiladi.
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
    # SAVE MEDIA INFORMATION
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
        "O'yinni brauzerda ochib, "
        "o'zingiz o'ynaysiz va kerakli "
        "qismini video qilib olasiz.\n\n"
        "🖼 <b>Rasm/GIF</b>\n"
        "Tayyor rasm yoki GIF yuborishingiz mumkin.\n\n"
        "MP4 rejimi faqat "
        "🎬 MP4 YARATISH tugmasi bosilganda boshlanadi.",
        reply_markup=_thumbnail_keyboard(),
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

    Bu bosqichda hali video yozilmaydi.

    Oqim:
        🎬 MP4 YARATISH
            ↓
        ▶️ BOSHLASH
            ↓
        O'yin oynasi
            ↓
        🎥 YOZISH
    """

    await callback.answer(
        "🎬 MP4 rejimi tayyorlanmoqda..."
    )

    data = await state.get_data()

    # --------------------------------------------------------
    # HTML mavjudligini tekshirish
    # --------------------------------------------------------

    if not data.get("html_file_id"):
        await callback.message.answer(
            "❌ HTML fayl topilmadi.\n\n"
            "Iltimos, /yangi jarayonini qaytadan boshlang."
        )
        return

    # --------------------------------------------------------
    # FSM → RECORDING START
    # --------------------------------------------------------

    await state.set_state(
        AddGameFSM.waiting_recording_start
    )

    # --------------------------------------------------------
    # Admin uchun boshlash oynasi
    # --------------------------------------------------------

    await callback.message.answer(
        "🎬 <b>MP4 yaratish rejimi</b>\n\n"
        "HTML o'yin tayyor.\n\n"
        "📐 Video o'lchami: <b>640×360</b>\n"
        "🎮 O'yinni o'zingiz boshqarasiz.\n"
        "🎥 Kerakli joyida yozishni boshlaysiz.\n\n"
        "▶️ <b>BOSHLASH</b> tugmasini bosing.",
        reply_markup=_recording_start_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# MP4 RECORDING — PREPARE GAME
# ============================================================

@router.callback_query(
    F.data == "admin:recording_start",
    AddGameFSM.waiting_recording_start,
)
async def cb_recording_start(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    """
    Admin ▶️ BOSHLASH tugmasini bosganda ishlaydi.

    HTML fayl Telegram'dan yuklab olinadi va
    recording sessiyasi uchun FSM'ga saqlanadi.

    Keyingi bosqichda bu ma'lumot asosida
    haqiqiy WebApp recording oynasi ochiladi.
    """

    await callback.answer(
        "▶️ O'yin tayyorlanmoqda..."
    )

    data = await state.get_data()

    # --------------------------------------------------------
    # HTML ID tekshiruvi
    # --------------------------------------------------------

    html_file_id = data.get(
        "html_file_id"
    )

    slug = data.get(
        "slug"
    )

    if not html_file_id:
        await callback.message.answer(
            "❌ HTML fayl topilmadi."
        )
        return

    if not slug:
        await callback.message.answer(
            "❌ O'yin slug'i topilmadi."
        )
        return

    status = await callback.message.answer(
        "⏳ <b>O'yin recording uchun tayyorlanmoqda...</b>\n\n"
        "📄 HTML yuklanmoqda...\n"
        "🎮 O'yin oynasi tayyorlanadi.\n"
        "📐 640×360 format.\n\n"
        "Iltimos, kuting...",
        parse_mode="HTML",
    )

    try:
        # ----------------------------------------------------
        # HTML faylni Telegram'dan yuklab olish
        # ----------------------------------------------------

        html_bytes = await _download_telegram_bytes(
            bot,
            html_file_id,
        )

        if not html_bytes:
            raise RuntimeError(
                "HTML fayl bo'sh."
            )

        # ----------------------------------------------------
        # Recording ma'lumotlarini FSM'ga saqlash
        # ----------------------------------------------------

        await state.update_data(
            recording_slug=slug,
            recording_html_bytes=html_bytes,
            recording_active=False,
            recording_source=None,
            recording_mp4_path=None,
        )

        # ----------------------------------------------------
        # Keyingi FSM holati
        # ----------------------------------------------------

        await state.set_state(
            AddGameFSM.waiting_recording
        )

        await status.edit_text(
            "🎮 <b>O'yin tayyor!</b>\n\n"
            "Keyingi bosqichda o'yin oynasi ochiladi.\n\n"
            "🎥 <b>YOZISH</b> — recordingni boshlaydi.\n"
            "⏹ <b>TO'XTATISH</b> — recordingni tugatadi.",
            reply_markup=_recording_keyboard(
                recording=False
            ),
            parse_mode="HTML",
        )

    except Exception as exc:
        logger.exception(
            "Failed to prepare game recording: %s",
            exc,
        )

        await status.edit_text(
            "❌ <b>O'yinni tayyorlashda xato</b>\n\n"
            f"<code>{str(exc)[:500]}</code>",
            parse_mode="HTML",
        )

# ============================================================
# RECORDING — START BROWSER SESSION
# ============================================================

@router.callback_query(
    F.data == "admin:recording_start",
    AddGameFSM.waiting_recording_start,
)
async def cb_recording_start(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    """
    ▶️ BOSHLASH tugmasi.

    Admin MP4 rejimini boshlaganda:
      1. HTML tekshiriladi.
      2. Browser recording session tayyorlanadi.
      3. FSM waiting_recording holatiga o'tadi.

    Haqiqiy Playwright browser ishga tushirish
    alohida servis orqali keyingi bosqichda bajariladi.
    """

    await callback.answer(
        "▶️ O'yin tayyorlanmoqda..."
    )

    data = await state.get_data()

    if not data.get("html_file_id"):
        await callback.message.answer(
            "❌ HTML fayl topilmadi.\n\n"
            "Iltimos, /yangi jarayonini qaytadan boshlang."
        )
        return

    # --------------------------------------------------------
    # TEMPORARY BROWSER SESSION PREPARATION
    # --------------------------------------------------------

    try:
        await state.update_data(
            recording_started=False,
            recording_source=None,
        )

        # Browser session tayyorlash callback'iga o'tamiz.
        await cb_recording_browser(
            callback,
            state,
            bot,
        )

    except Exception as exc:
        logger.exception(
            "Failed to start browser recording session: %s",
            exc,
        )

        await callback.message.answer(
            "❌ <b>Browser sessionni boshlashda xato</b>\n\n"
            f"<code>{str(exc)[:700]}</code>",
            parse_mode="HTML",
        )

# ============================================================
# RECORDING — CONVERT WEBM → MP4
# ============================================================

@router.callback_query(
    F.data == "admin:recording_convert",
    AddGameFSM.waiting_recording,
)
async def cb_recording_convert(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Yozilgan WEBM faylni game_video_service orqali
    640x360 MP4 formatiga aylantiradi.

    recording_source:
        WEBM faylning Path manzili.

    Agar WEBM mavjud bo'lmasa, MP4 yaratish boshlanmaydi.
    """

    await callback.answer(
        "🎬 MP4 tayyorlanmoqda..."
    )

    data = await state.get_data()

    slug = data.get("slug")
    recording_source = data.get(
        "recording_source"
    )

    # --------------------------------------------------------
    # SLUG TEKSHIRISH
    # --------------------------------------------------------

    if not slug:
        await callback.message.answer(
            "❌ O'yin slug'i topilmadi."
        )
        return

    # --------------------------------------------------------
    # WEBM TEKSHIRISH
    # --------------------------------------------------------

    if not recording_source:
        await callback.message.answer(
            "❌ <b>WEBM recording topilmadi.</b>\n\n"
            "Avval o'yin yozib olinishi kerak.\n\n"
            "Hozirgi bosqichda recording oynasi "
            "hali serverga WEBM fayl yubormagan.",
            parse_mode="HTML",
        )
        return

    source = Path(
        str(recording_source)
    )

    if not source.exists():
        await callback.message.answer(
            "❌ <b>WEBM fayl topilmadi.</b>\n\n"
            f"<code>{source}</code>",
            parse_mode="HTML",
        )
        return

    status = await callback.message.answer(
        "🎬 <b>MP4 tayyorlanmoqda...</b>\n\n"
        "📹 WEBM recording topildi.\n"
        "📐 640×360 formatga o'tkazilmoqda.\n"
        "🎞 H.264 MP4 yaratilmoqda.\n\n"
        "⏳ Iltimos, kuting...",
        parse_mode="HTML",
    )

    try:
        # ----------------------------------------------------
        # GAME VIDEO SERVICE
        # ----------------------------------------------------

        from services.game_video_service import (
            convert_recorded_video_to_mp4,
        )

        destination = (
            Path(__file__).resolve().parent.parent
            / "webapp"
            / "generated_videos"
            / f"{slug}.mp4"
        )

        mp4_path = (
            await convert_recorded_video_to_mp4(
                source=source,
                destination=destination,
            )
        )

        if not mp4_path.exists():
            raise RuntimeError(
                "MP4 fayl yaratilmadi."
            )

        if mp4_path.stat().st_size < 1024:
            raise RuntimeError(
                "MP4 fayl juda kichik yoki bo'sh."
            )

        # ----------------------------------------------------
        # FSM
        # ----------------------------------------------------

        await state.update_data(
            image_kind="mp4",
            image_ext=".mp4",
            image_file_id=None,
            image_path=str(mp4_path),
            recording_mp4_path=str(mp4_path),
        )

        await state.set_state(
            AddGameFSM.waiting_confirm
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        await status.edit_text(
            "✅ <b>MP4 muvaffaqiyatli yaratildi!</b>\n\n"
            f"🎬 <code>{slug}.mp4</code>\n"
            "📐 640×360\n\n"
            "Endi preview ko'rsatiladi.",
            parse_mode="HTML",
        )

        # ----------------------------------------------------
        # PREVIEW
        # ----------------------------------------------------

        data = await state.get_data()

        await _send_preview(
            callback.message,
            data,
        )

        logger.info(
            "[MP4] Recording converted successfully: "
            "slug=%s path=%s",
            slug,
            mp4_path,
        )

    except Exception as exc:
        logger.exception(
            "WEBM to MP4 conversion failed: %s",
            exc,
        )

        await status.edit_text(
            "❌ <b>MP4 yaratishda xatolik</b>\n\n"
            f"<code>{str(exc)[:1000]}</code>",
            parse_mode="HTML",
        )

# ============================================================
# RECORDING — PREPARE BROWSER SESSION
# ============================================================

@router.callback_query(
    F.data == "admin:recording_browser",
    AddGameFSM.waiting_recording_start,
)
async def cb_recording_browser(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    """
    HTML o'yin uchun browser recording sessionini tayyorlaydi.

    Bu bosqich:
      1. Telegram'dan HTML faylni yuklaydi.
      2. Vaqtinchalik papka yaratadi.
      3. HTML faylni shu papkaga yozadi.
      4. Browser session uchun kerakli ma'lumotlarni FSM'ga saqlaydi.

    Haqiqiy Playwright browser ishga tushirish
    keyingi bosqichda bajariladi.
    """

    await callback.answer(
        "🖥 Browser tayyorlanmoqda..."
    )

    data = await state.get_data()

    slug = data.get("slug")
    html_file_id = data.get("html_file_id")

    if not slug or not html_file_id:
        await callback.message.answer(
            "❌ HTML yoki slug topilmadi."
        )
        return

    status = await callback.message.answer(
        "🖥 <b>Recording oynasi tayyorlanmoqda...</b>\n\n"
        "📄 HTML yuklanmoqda...\n"
        "🎮 O'yin tayyorlanmoqda...\n"
        "📐 640×360 recording sozlanmoqda...\n\n"
        "⏳ Biroz kuting...",
        parse_mode="HTML",
    )

    temp_dir = None

    try:
        # ----------------------------------------------------
        # HTML DOWNLOAD
        # ----------------------------------------------------

        html_bytes = await _download_telegram_bytes(
            bot,
            html_file_id,
        )

        if not html_bytes:
            raise RuntimeError(
                "HTML fayl bo'sh."
            )

        # ----------------------------------------------------
        # TEMP DIRECTORY
        # ----------------------------------------------------

        import tempfile

        temp_dir = Path(
            tempfile.mkdtemp(
                prefix=f"game_recording_{slug}_"
            )
        )

        html_path = (
            temp_dir
            / f"{slug}.html"
        )

        html_path.write_bytes(
            html_bytes
        )

        # ----------------------------------------------------
        # RECORDING DIRECTORY
        # ----------------------------------------------------

        video_dir = (
            temp_dir
            / "recording"
        )

        video_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # SAVE SESSION DATA
        # ----------------------------------------------------

        await state.update_data(
            recording_temp_dir=str(
                temp_dir
            ),
            recording_html_path=str(
                html_path
            ),
            recording_video_dir=str(
                video_dir
            ),
            recording_started=False,
            recording_source=None,
        )

        await state.set_state(
            AddGameFSM.waiting_recording
        )

        # ----------------------------------------------------
        # READY
        # ----------------------------------------------------

        await status.edit_text(
            "✅ <b>Recording oynasi tayyor!</b>\n\n"
            "🎮 O'yin: "
            f"<b>{data.get('name', slug)}</b>\n"
            "📐 O'lcham: <b>640×360</b>\n\n"
            "Endi browser session ishga tushiriladi.\n\n"
            "🎥 <b>YOZISH</b> — recordingni boshlash\n"
            "⏹ <b>TO'XTATISH</b> — recordingni tugatish",
            parse_mode="HTML",
            reply_markup=_recording_keyboard(),
        )

        logger.info(
            "[RECORDING] Browser session prepared: "
            "slug=%s html=%s",
            slug,
            html_path,
        )

    except Exception as exc:
        logger.exception(
            "Failed to prepare browser recording: %s",
            exc,
        )

        await status.edit_text(
            "❌ <b>Recording oynasini tayyorlashda xato</b>\n\n"
            f"<code>{str(exc)[:800]}</code>",
            parse_mode="HTML",
        )

# ============================================================
# RECORDING SESSION STORAGE
# ============================================================

_RECORDING_SESSIONS: dict[int, dict] = {}


# ============================================================
# RECORDING — LAUNCH PLAYWRIGHT GAME
# ============================================================

@router.callback_query(
    F.data == "admin:browser_launch",
    AddGameFSM.waiting_recording,
)
async def cb_browser_launch(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Playwright Chromium sessionini ishga tushiradi.

    Muhim:
    Browser obyektlari FSM ichiga saqlanmaydi.
    Ular server xotirasidagi _RECORDING_SESSIONS
    dictionary'sida saqlanadi.
    """

    await callback.answer(
        "🎮 O'yin tayyorlanmoqda..."
    )

    if not callback.from_user:
        return

    user_id = callback.from_user.id

    data = await state.get_data()

    html_path = data.get(
        "recording_html_path"
    )

    video_dir = data.get(
        "recording_video_dir"
    )

    if not html_path or not video_dir:
        await callback.message.answer(
            "❌ Recording session ma'lumotlari topilmadi."
        )
        return

    html_file = Path(
        html_path
    )

    recording_dir = Path(
        video_dir
    )

    if not html_file.exists():
        await callback.message.answer(
            "❌ HTML fayl topilmadi."
        )
        return

    recording_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # ESKI SESSIONNI TOZALASH
    # --------------------------------------------------------

    old_session = _RECORDING_SESSIONS.pop(
        user_id,
        None,
    )

    if old_session:
        try:
            old_context = old_session.get(
                "context"
            )

            old_browser = old_session.get(
                "browser"
            )

            old_playwright = old_session.get(
                "playwright"
            )

            if old_context:
                await old_context.close()

            if old_browser:
                await old_browser.close()

            if old_playwright:
                await old_playwright.stop()

        except Exception:
            logger.exception(
                "Failed to cleanup old recording session."
            )

    try:
        from playwright.async_api import (
            async_playwright,
        )

        playwright = (
            await async_playwright().start()
        )

        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 640,
                "height": 360,
            },
            device_scale_factor=1,
            record_video_dir=str(
                recording_dir
            ),
            record_video_size={
                "width": 640,
                "height": 360,
            },
        )

        page = await context.new_page()

        # ----------------------------------------------------
        # HTML O'YINNI OCHISH
        # ----------------------------------------------------

        await page.goto(
            html_file.as_uri(),
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        await page.wait_for_timeout(
            1500
        )

        # ----------------------------------------------------
        # SESSIONNI SERVER XOTIRASIGA SAQLASH
        # ----------------------------------------------------

        _RECORDING_SESSIONS[user_id] = {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "page": page,
            "video_dir": recording_dir,
            "video_path": None,
            "recording": False,
            "slug": data.get("slug"),
        }

        await state.update_data(
            recording_started=False,
            recording_source=None,
        )

        await callback.message.edit_text(
            "🎮 <b>O'YIN TAYYOR!</b>\n\n"
            "📐 O'lcham: <b>640×360</b>\n"
            "🎥 Video recording session faol.\n\n"
            "Endi recording boshqaruvi "
            "Telegram tugmalari orqali ishlaydi.\n\n"
            "🎥 <b>YOZISH</b> — recordingni boshlash\n"
            "⏹ <b>TO'XTATISH</b> — recordingni tugatish",
            parse_mode="HTML",
            reply_markup=_recording_keyboard(),
        )

        logger.info(
            "[RECORDING] Browser session started: "
            "user=%s slug=%s",
            user_id,
            data.get("slug"),
        )

    except Exception as exc:
        logger.exception(
            "Failed to launch Playwright game: %s",
            exc,
        )

        _RECORDING_SESSIONS.pop(
            user_id,
            None,
        )

        await callback.message.edit_text(
            "❌ <b>Chromium ishga tushmadi</b>\n\n"
            f"<code>{str(exc)[:1000]}</code>",
            parse_mode="HTML",
        )

# ============================================================
# RECORDING — START / TOGGLE
# ============================================================

@router.callback_query(
    F.data == "admin:recording_toggle",
    AddGameFSM.waiting_recording,
)
async def cb_recording_toggle(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    🎥 YOZISH tugmasi.

    Playwright video recording sahifa ochilgan
    paytdan boshlab avtomatik ravishda yoziladi.

    Bu tugma:
      • recording holatini ACTIVE qiladi
      • o'yinga fokus beradi
      • FSM'da recording boshlanganini belgilaydi

    Playwright record_video:
    context yaratilgan paytdan boshlab yozadi.
    Shuning uchun bu yerda MediaRecorder
    boshlashga ehtiyoj yo'q.
    """

    await callback.answer(
        "🎥 Yozish boshlandi!"
    )

    if not callback.from_user:
        return

    user_id = callback.from_user.id

    session = _RECORDING_SESSIONS.get(
        user_id
    )

    if not session:
        await callback.message.answer(
            "❌ Recording session topilmadi.\n\n"
            "Iltimos, MP4 yaratishni qaytadan boshlang."
        )
        return

    page = session.get(
        "page"
    )

    if not page:
        await callback.message.answer(
            "❌ O'yin oynasi topilmadi."
        )
        return

    # --------------------------------------------------------
    # ALREADY RECORDING
    # --------------------------------------------------------

    if session.get("recording"):
        await callback.answer(
            "🎥 Recording allaqachon ishlayapti.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # RECORDING ACTIVE
    # --------------------------------------------------------

    session["recording"] = True

    await state.update_data(
        recording_started=True,
    )

    # --------------------------------------------------------
    # GAME FOCUS
    # --------------------------------------------------------

    try:
        await page.bring_to_front()

    except Exception:
        pass

    # --------------------------------------------------------
    # TRY TO FOCUS GAME CANVAS
    # --------------------------------------------------------

    try:
        await page.mouse.click(
            320,
            180,
        )
    except Exception:
        pass

    # --------------------------------------------------------
    # UI UPDATE
    # --------------------------------------------------------

    try:
        await callback.message.edit_text(
            "🔴 <b>YOZISH DAVOM ETMOQDA</b>\n\n"
            "🎮 O'yinni o'ynang.\n"
            "📐 640×360\n"
            "🎥 Video recording faol.\n\n"
            "Tayyor bo'lganda:\n"
            "⏹ <b>TO'XTATISH</b> tugmasini bosing.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
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
            ),
        )

    except Exception:
        logger.exception(
            "Failed to update recording UI."
        )

    logger.info(
        "[RECORDING] Recording marked active: "
        "user=%s slug=%s",
        user_id,
        session.get("slug"),
    )

# ============================================================
# RECORDING — STOP
# ============================================================

@router.callback_query(
    F.data == "admin:recording_stop",
    AddGameFSM.waiting_recording,
)
async def cb_recording_stop(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    ⏹ TO'XTATISH tugmasi.

    Recording session yopiladi.
    Playwright yaratgan WEBM fayl olinadi.
    Keyingi bosqichda WEBM → MP4 qilinadi.
    """

    await callback.answer(
        "⏹ Yozish to'xtatilmoqda..."
    )

    if not callback.from_user:
        return

    user_id = callback.from_user.id

    session = _RECORDING_SESSIONS.get(
        user_id
    )

    if not session:
        await callback.message.answer(
            "❌ Recording session topilmadi.\n\n"
            "Iltimos, MP4 yaratishni qaytadan boshlang."
        )
        return

    page = session.get("page")
    context = session.get("context")
    browser = session.get("browser")

    if not page or not context:
        await callback.message.answer(
            "❌ Recording oynasi topilmadi."
        )
        return

    session["recording"] = False

    await callback.message.edit_text(
        "⏳ <b>Video yozuvi yakunlanmoqda...</b>\n\n"
        "🎥 WEBM fayl tayyorlanmoqda.\n"
        "Iltimos, kuting...",
        parse_mode="HTML",
    )

    video_path = None

    try:
        # ----------------------------------------------------
        # VIDEO OBJECT
        # ----------------------------------------------------

        video = page.video

        if not video:
            raise RuntimeError(
                "Playwright video recording topilmadi."
            )

        # ----------------------------------------------------
        # VIDEO PATH
        # ----------------------------------------------------

        video_path = await video.path()

        if not video_path:
            raise RuntimeError(
                "WEBM video yo'li olinmadi."
            )

        webm_path = Path(
            video_path
        )

        # ----------------------------------------------------
        # CLOSE CONTEXT
        #
        # Playwright video fayli context yopilgandan
        # keyin to'liq yakunlanadi.
        # ----------------------------------------------------

        await context.close()

        # Browser ham yopiladi.
        if browser:
            await browser.close()

        # ----------------------------------------------------
        # VERIFY WEBM
        # ----------------------------------------------------

        if not webm_path.exists():
            raise RuntimeError(
                "WEBM fayl yaratilmadi."
            )

        if webm_path.stat().st_size < 1024:
            raise RuntimeError(
                "WEBM fayl juda kichik yoki bo'sh."
            )

        # ----------------------------------------------------
        # SAVE PATH TO FSM
        # ----------------------------------------------------

        await state.update_data(
            recorded_webm=str(webm_path),
            recording_started=False,
        )

        logger.info(
            "[RECORDING] WEBM ready: "
            "user=%s path=%s size=%s",
            user_id,
            webm_path,
            webm_path.stat().st_size,
        )

        # ----------------------------------------------------
        # REMOVE SESSION
        # ----------------------------------------------------

        _RECORDING_SESSIONS.pop(
            user_id,
            None,
        )

        # ----------------------------------------------------
        # NEXT STEP
        # ----------------------------------------------------

        await callback.message.edit_text(
            "✅ <b>Video yozib olindi!</b>\n\n"
            "🎥 WEBM tayyor.\n"
            "📐 640×360\n\n"
            "⏳ Endi WEBM → MP4 konvertatsiya qilinadi...",
            parse_mode="HTML",
        )

        await _finalize_recorded_mp4(
            callback.message,
            state,
        )

    except Exception as exc:
        logger.exception(
            "[RECORDING] Failed to stop recording: %s",
            exc,
        )

        # Browser/context tozalash
        try:
            if context:
                await context.close()
        except Exception:
            pass

        try:
            if browser:
                await browser.close()
        except Exception:
            pass

        _RECORDING_SESSIONS.pop(
            user_id,
            None,
        )

        await callback.message.edit_text(
            "❌ <b>Video yozishni to'xtatishda xato</b>\n\n"
            f"<code>{str(exc)[:800]}</code>",
            parse_mode="HTML",
        )

# ============================================================
# RECORDING — FINALIZE WEBM → MP4
# ============================================================

async def _finalize_recorded_mp4(
    message: Message,
    state: FSMContext,
) -> None:
    """
    Yozib olingan WEBM faylni yakuniy MP4 ga aylantiradi.

    Natija:
        640×360 MP4

    Keyinchalik preview va /yangi → Saqlash
    bosqichida shu MP4 ishlatiladi.
    """

    data = await state.get_data()

    slug = data.get("slug")
    webm_path_value = data.get(
        "recorded_webm"
    )

    if not slug:
        await message.answer(
            "❌ O'yin slug'i topilmadi."
        )
        return

    if not webm_path_value:
        await message.answer(
            "❌ Yozilgan WEBM fayl topilmadi."
        )
        return

    webm_path = Path(
        webm_path_value
    )

    if not webm_path.exists():
        await message.answer(
            "❌ WEBM fayli mavjud emas."
        )
        return

    if webm_path.stat().st_size < 1024:
        await message.answer(
            "❌ WEBM fayli bo'sh yoki buzilgan."
        )
        return

    # --------------------------------------------------------
    # MP4 OUTPUT
    # --------------------------------------------------------

    try:
        from services.game_video_service import (
            convert_recorded_video_to_mp4,
        )

        mp4_path = (
            webm_path.parent
            / f"{slug}.mp4"
        )

        await message.edit_text(
            "🎬 <b>MP4 tayyorlanmoqda...</b>\n\n"
            "📹 WEBM → MP4\n"
            "📐 640×360\n"
            "⚙️ H.264\n\n"
            "⏳ Iltimos, kuting...",
            parse_mode="HTML",
        )

        # ----------------------------------------------------
        # CONVERT
        # ----------------------------------------------------

        result = await convert_recorded_video_to_mp4(
            source=webm_path,
            destination=mp4_path,
        )

        if not result:
            raise RuntimeError(
                "MP4 conversion natija qaytarmadi."
            )

        mp4_path = Path(
            result
        )

        # ----------------------------------------------------
        # VERIFY MP4
        # ----------------------------------------------------

        if not mp4_path.exists():
            raise RuntimeError(
                "MP4 fayli yaratilmadi."
            )

        if mp4_path.stat().st_size < 1024:
            raise RuntimeError(
                "MP4 fayli juda kichik yoki bo'sh."
            )

        # ----------------------------------------------------
        # FSM
        # ----------------------------------------------------

        await state.update_data(
            image_file_id=None,
            image_ext=".mp4",
            image_kind="mp4",
            image_path=str(mp4_path),
            recorded_mp4=str(mp4_path),
            recording_started=False,
        )

        await state.set_state(
            AddGameFSM.waiting_confirm
        )

        logger.info(
            "[RECORDING] MP4 finalized: "
            "slug=%s path=%s size=%s",
            slug,
            mp4_path,
            mp4_path.stat().st_size,
        )

        # ----------------------------------------------------
        # SEND MP4 PREVIEW
        # ----------------------------------------------------

        await message.answer_video(
            video=FSInputFile(
                str(mp4_path)
            ),
            caption=(
                "✅ <b>MP4 tayyor!</b>\n\n"
                f"🎮 O'yin: <b>{data.get('name', slug)}</b>\n"
                "📐 640×360\n"
                "🎬 MP4 recording\n\n"
                "Saqlashni tasdiqlaysizmi?"
            ),
            reply_markup=_confirm_keyboard(),
            parse_mode="HTML",
            supports_streaming=True,
        )

    except Exception as exc:
        logger.exception(
            "[RECORDING] WEBM → MP4 failed: %s",
            exc,
        )

        await message.edit_text(
            "❌ <b>MP4 yaratishda xato</b>\n\n"
            f"<code>{str(exc)[:1000]}</code>\n\n"
            "Rasm yoki GIF yuborib davom etishingiz mumkin.",
            parse_mode="HTML",
        )