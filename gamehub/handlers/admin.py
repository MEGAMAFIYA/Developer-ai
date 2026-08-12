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

MP4 rejimi (browser-based recording):
- HTML fayl darhol webapp/games/{slug}.html
ga saqlanadi, shunda
u /games/{slug} orqali xizmat qilinishi
mumkin.
- Admin uchun Telegram Mini App tugmasi
yuboriladi — bu tugma
to'g'ridan-to'g'ri ADMINNING O'Z
TELEFONIDA ochiladi (serverda emas),
shuning uchun admin o'yinni chindan ham
o'zi ko'rib, o'ynay oladi.
- Mini App sahifasi
(api/routes/recorder.py) o'yin <canvas>'ini
captureStream() + MediaRecorder bilan
yozib oladi va WEBM'ni
/api/recording/upload'ga yuboradi.
- Bot fon vazifasi (background task) orqali
yuklanishini kutadi,
keyin FFmpeg bilan 640x360 MP4'ga
o'tkazadi (services/game_video_service.py)
va preview ko'rsatadi.

Eslatma: serverda headless
Playwright/Chromium orqali o'yinni
"o'zi o'ynash" imkonsiz edi — chunki
Chromium oynasi serverda,
adminning telefonida emas edi. Shu sabab
MP4 rejimi butunlay
brauzer-tomonidagi (client-side) yozib
olishga o'tkazildi.
"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from config import config
from database.global_db import (
    add_game,
    get_game_by_slug,
)

from services import recording_bridge
from services.game_video_service import convert_recorded_video_to_mp4
from services.upload_service import (
    ASSETS_DIR,
    GAMES_DIR,
    image_db_url,
    image_ext_from_filename_or_mime,
    save_html,
    save_image,
)

logger = logging.getLogger(__name__)
router = Router()

# Background poll tasks waiting for an
# uploaded WEBM, keyed by admin user_id.
_ACTIVE_POLL_TASKS: dict[int, asyncio.Task] = {}

POLL_INTERVAL_SECONDS = 2
POLL_MAX_SECONDS = 15 * 60  # give up waiting after 15 minutes


# =================================================
# FSM
# =================================================

class AddGameFSM(StatesGroup):
    waiting_name = State()
    waiting_slug = State()
    waiting_description = State()
    waiting_category = State()
    waiting_html = State()
    # Thumbnail
    waiting_image = State()
    # MP4 recording (admin is inside the
    # Mini App recorder page)
    waiting_recording = State()
    # Final preview / save
    waiting_confirm = State()


# =================================================
# ADMIN
# =================================================

def _is_admin(user_id: int) -> bool:
    """
    Faqat config.ADMIN_ID ga ega
    foydalanuvchiga /yangi va MP4 recording funksiyalaridan
    foydalanishga
    ruxsat beradi.
    """
    return user_id == config.ADMIN_ID


# =================================================
# CLEANUP HELPERS
# =================================================

def _cleanup_admin_state(user_id: int) -> None:
    """
    Avvalgi recording fon vazifasi va
    sessiyasini tozalaydi.
    /yangi qayta boshlanganda, /bekor
    bosilganda yoki admin:cancel
    bosilganda chaqiriladi — resurs va
    vaqtinchalik fayl leak
    bo'lmasligi uchun.
    """
    task = _ACTIVE_POLL_TASKS.pop(user_id, None)
    if task and not task.done():
        task.cancel()

    recording_bridge.cancel_sessions_for_user(user_id)


async def _delete_orphan_html(slug: str | None) -> None:
    """
    MP4 recording uchun oldindan saqlangan
    HTML faylni o'chiradi,
    agar o'yin hech qachon bazaga
    saqlanmagan bo'lsa.
    """
    if not slug:
        return

    try:
        existing = await get_game_by_slug(slug)
        if existing:
            return

        html_path = GAMES_DIR / f"{slug}.html"
        if html_path.exists():
            html_path.unlink()
            logger.info(
                "[CLEANUP] Orphaned HTML removed: %s",
                html_path,
            )
    except Exception:
        logger.exception(
            "[CLEANUP] Failed to remove orphaned HTML for slug=%s",
            slug,
        )


# =================================================
# THUMBNAIL KEYBOARD
# =================================================

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


# =================================================
# RECORDER KEYBOARD
# =================================================

def _recorder_keyboard(
    recorder_url: str,
) -> InlineKeyboardMarkup:
    """
    Admin brauzerda o'yinni ochib yozib
    olishi uchun tugmalar.
    ▶️ tugmasi Telegram Mini App'ni
    ADMINNING O'Z TELEFONIDA ochadi
    (serverda emas) — shu yerda 🎥 YOZISH /
    ⏹ TO'XTATISH tugmalari
    sahifaning o'zida joylashgan.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ O'yinni ochish va yozish",
                    web_app=WebAppInfo(
                        url=recorder_url
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Holatni tekshirish",
                    callback_data="admin:recording_check",
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

# =================================================
# CONFIRM KEYBOARD
# =================================================

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


# =================================================
# PREVIEW CAPTION
# =================================================

def _preview_caption(data: dict) -> str:
    """
    Yangi o'yin preview kartasi uchun
    caption.
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


# =================================================
# PREVIEW
# =================================================

async def _send_preview(
    message: Message,
    data: dict,
) -> None:
    """
    Yangi o'yin preview kartasini yuboradi.
    MP4 / GIF / rasm formatlarini alohida
    ko'rsatadi.
    """
    caption = _preview_caption(data)

    keyboard = _confirm_keyboard()

    image_id = data.get(
        "image_file_id"
    )

    image_kind = data.get(
        "image_kind"
    )

    image_path = data.get(
        "image_path"
    )

    # -------------------------------------
    # MP4 (local file on disk — recorded
    # in-browser)
    # -------------------------------------

    if image_kind == "mp4":
        if image_path and Path(image_path).exists():
            await message.answer_video(
                video=FSInputFile(
                    str(image_path)
                ),
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
                supports_streaming=True,
            )
            return

        if image_id:
            await message.answer_video(
                video=image_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
                supports_streaming=True,
            )
            return

    # -------------------------------------
    # TELEGRAM GIF
    # -------------------------------------

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

    # -------------------------------------
    # GIF DOCUMENT
    # -------------------------------------

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

    # -------------------------------------
    # NORMAL IMAGE
    # -------------------------------------

    if image_id:
        await message.answer_photo(
            photo=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # -------------------------------------
    # TEXT ONLY
    # -------------------------------------

    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# =================================================
# /YANGI
# =================================================

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

    old_data = await state.get_data()

    _cleanup_admin_state(
        message.from_user.id
    )

    await _delete_orphan_html(
        old_data.get("slug")
    )

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


# =================================================
# /BEKOR
# =================================================

@router.message(Command("bekor"))
async def cmd_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    current_state = await state.get_state()

    if current_state is None:
        return

    data = await state.get_data()

    if message.from_user:
        _cleanup_admin_state(
            message.from_user.id
        )

    await _delete_orphan_html(
        data.get("slug")
    )

    await state.clear()

    await message.answer(
        "❌ Jarayon bekor qilindi."
    )


# =================================================
# STEP 1 — NAME
# =================================================

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
        "<i>Masalan: zombi, ilon-o'yini</i>",
        parse_mode="HTML",
    )


# =================================================
# SLUG CHARACTERS
# =================================================

_SLUG_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_"
)


# =================================================
# STEP 2 — SLUG
# =================================================

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

# =================================================
# STEP 3 — DESCRIPTION
# =================================================

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


# =================================================
# STEP 4 — CATEGORY
# =================================================

@router.message(
    AddGameFSM.waiting_category
)
async def step_category(
    message: Message,
    state: FSMContext
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


# =================================================
# STEP 5 — HTML
# =================================================

@router.message(
    AddGameFSM.waiting_html
)
async def step_html(
    message: Message,
    state: FSMContext
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
        "o'yinni o'z telefoningizda ochib, "
        "o'zingiz o'ynab video yozishingiz "
        "mumkin.\n\n"
        "Yoki 🖼 rasm / 🎞 GIF "
        "yuborishingiz mumkin.",
        reply_markup=_thumbnail_keyboard(),
        parse_mode="HTML",
    )


# =================================================
# STEP 6 — THUMBNAIL / RASM / GIF
# =================================================

@router.message(
    AddGameFSM.waiting_image
)
async def step_image(
    message: Message,
    state: FSMContext
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

    # -------------------------------------
    # PHOTO
    # -------------------------------------

    if message.photo:
        file_id = message.photo[-1].file_id
        ext = ".jpg"
        image_kind = "photo"

    # -------------------------------------
    # TELEGRAM ANIMATION
    # -------------------------------------

    elif message.animation:
        file_id = message.animation.file_id
        ext = ".gif"
        image_kind = "animation"

    # -------------------------------------
    # DOCUMENT
    # -------------------------------------

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

    # -------------------------------------
    # NOTHING
    # -------------------------------------

    else:
        await message.answer(
            "⚠️ Rasm yoki GIF yuboring.\n\n"
            "Yoki quyidagi tugma orqali "
            "🎬 MP4 yaratishingiz mumkin.",
            reply_markup=_thumbnail_keyboard(),
        )
        return

    # -------------------------------------
    # SAVE MEDIA INFORMATION
    # -------------------------------------

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


# =================================================
# THUMBNAIL INFORMATION
# =================================================

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
        "O'yin o'z telefoningizda ochiladi, "
        "o'zingiz o'ynaysiz va kerakli "
        "qismini video qilib olasiz.\n\n"
        "🖼 <b>Rasm/GIF</b>\n"
        "Tayyor rasm yoki GIF yuborishingiz mumkin.\n\n"
        "MP4 rejimi faqat "
        "🎬 MP4 YARATISH tugmasi bosilganda "
        "boshlanadi.",
        reply_markup=_thumbnail_keyboard(),
        parse_mode="HTML",
    )

# =================================================
# MP4 CREATION — OPEN RECORDER MINI APP
# =================================================

@router.callback_query(
    F.data == "admin:create_mp4",
    AddGameFSM.waiting_image,
)
async def cb_create_mp4(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot
) -> None:
    """
    MP4 rejimini boshlaydi.
    Oqim:
        🎬 MP4 YARATISH
            ↓
        HTML webapp/games/{slug}.html ga
        saqlanadi
        (shunda /games/{slug} uni xizmat
        qila oladi)
            ↓
        Telegram Mini App tugmasi
        yuboriladi
        (ADMINNING O'Z TELEFONIDA ochiladi)
            ↓
        Admin sahifada 🎥 YOZISH / ⏹
        TO'XTATISH orqali
        o'zi yozib oladi, WEBM avtomatik
        yuboriladi
            ↓
        Bot fon vazifasi orqali kutadi,
        FFmpeg bilan
        MP4'ga o'tkazadi va previewni
        ko'rsatadi
    """

    await callback.answer(
        "🎬 MP4 rejimi tayyorlanmoqda..."
    )

    if not callback.from_user or not callback.message:
        return

    data = await state.get_data()

    html_file_id = data.get("html_file_id")
    slug = data.get("slug")

    if not html_file_id or not slug:
        await callback.message.answer(
            "❌ HTML fayl yoki slug topilmadi.\n\n"
            "Iltimos, /yangi jarayonini "
            "qaytadan boshlang."
        )
        return

    status = await callback.message.answer(
        "⏳ <b>O'yin tayyorlanmoqda...</b>\n\n"
        "📄 HTML yuklanmoqda...",
        parse_mode="HTML",
    )

    # -------------------------------------
    # HTML'ni /games/{slug} orqali xizmat
    # qilish uchun
    # darhol saqlaymiz. O'yin hali bazaga
    # saqlanmagan bo'lsa,
    # /bekor yoki admin:cancel bu faylni
    # tozalaydi.
    # -------------------------------------

    try:
        await save_html(
            bot,
            html_file_id,
            slug,
        )

    except Exception as exc:
        logger.exception(
            "Failed to pre-save HTML for recording: %s",
            exc,
        )

        await status.edit_text(
            "❌ <b>HTML tayyorlashda xato</b>\n\n"
            f"<code>{str(exc)[:500]}</code>",
            parse_mode="HTML",
        )
        return

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    # Avvalgi urinishdan qolgan
    # session/task bo'lsa tozalaymiz.
    _cleanup_admin_state(user_id)

    token = recording_bridge.create_session(
        user_id=user_id,
        chat_id=chat_id,
        slug=slug,
    )

    await state.update_data(
        recording_token=token,
    )

    await state.set_state(
        AddGameFSM.waiting_recording
    )

    recorder_url = (
        f"{config.WEBAPP_URL.rstrip('/')}"
        f"/record/{slug}?token={token}"
    )

    await status.edit_text(
        "🎮 <b>O'yin tayyor!</b>\n\n"
        "▶️ tugmasini bosing — o'yin "
        "to'g'ridan-to'g'ri "
        "SIZNING telefoningizda "
        "ochiladi.\n\n"
        "🎥 <b>YOZISH</b> — sahifa ichida "
        "video yozishni boshlaydi\n"
        "⏹ <b>TO'XTATISH</b> — yozishni "
        "tugatadi va avtomatik yuboradi\n\n"
        "Yuborilgach, shu suhbatga o'zimiz "
        "qaytamiz — "
        "hech narsa bosishingiz shart "
        "emas.",
        reply_markup=_recorder_keyboard(
            recorder_url
        ),
        parse_mode="HTML",
    )

    task = asyncio.create_task(
        _poll_recording_upload(
            bot,
            chat_id,
            user_id,
            token,
            state,
        )
    )

    _ACTIVE_POLL_TASKS[user_id] = task


# =================================================
# RECORDING — FINALIZE UPLOADED WEBM → MP4
# =================================================

async def _finalize_uploaded_recording(
    bot: Bot,
    chat_id: int,
    token: str,
    state: FSMContext,
) -> None:
    """
    Yuklangan WEBM'ni MP4'ga aylantiradi va
    FSM'ni waiting_confirm holatiga
    o'tkazadi.
    """

    session = recording_bridge.get_session(
        token
    )

    if (
        not session
        or session.status != "uploaded"
        or not session.webm_path
    ):
        return

    slug = session.slug

    status_msg = await bot.send_message(
        chat_id,
        "🎬 <b>Video qabul qilindi!</b>\n\n"
        "📐 640×360 formatga "
        "o'tkazilmoqda...\n"
        "⏳ Iltimos, kuting...",
        parse_mode="HTML",
    )

    try:
        destination = (
            ASSETS_DIR
            / f"{slug}.mp4"
        )

        mp4_path = await convert_recorded_video_to_mp4(
            source=session.webm_path,
            destination=destination,
        )

        await state.update_data(
            image_file_id=None,
            image_ext=".mp4",
            image_kind="mp4",
            image_path=str(mp4_path),
        )

        await state.set_state(
            AddGameFSM.waiting_confirm
        )

        await status_msg.edit_text(
            "✅ <b>MP4 tayyor!</b>\n\n"
            "Endi preview ko'rsatiladi.",
            parse_mode="HTML",
        )

        data = await state.get_data()

        await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(
                str(mp4_path)
            ),
            caption=_preview_caption(
                data
            ),
            reply_markup=_confirm_keyboard(),
            parse_mode="HTML",
            supports_streaming=True,
        )

        logger.info(
            "[RECORDING] MP4 finalized: "
            "slug=%s path=%s",
            slug,
            mp4_path,
        )

    except Exception as exc:
        logger.exception(
            "[RECORDING] Finalize failed: %s",
            exc,
        )

        await status_msg.edit_text(
            "❌ <b>MP4 yaratishda xato</b>\n\n"
            f"<code>{str(exc)[:800]}</code>\n\n"
            "🎬 MP4 YARATISH tugmasi orqali "
            "qaytadan urinib "
            "ko'rishingiz yoki rasm/GIF "
            "yuborishingiz mumkin.",
            parse_mode="HTML",
        )

    finally:
        recording_bridge.pop_session(
            token
        )

        try:
            if (
                session.webm_path
                and session

# =================================================
# RECORDING — BACKGROUND POLL TASK
# =================================================

async def _poll_recording_upload(
    bot: Bot,
    chat_id: int,
    user_id: int,
    token: str,
    state: FSMContext,
) -> None:
    """
    WEBM yuklanishini fonda kutadi.
    Admin Mini App'da 🎥 YOZISH → ⏹
    TO'XTATISH bosgach,
    brauzer WEBM'ni
    /api/recording/upload'ga yuboradi.
    Bu vazifa shu holatni kuzatib, tayyor
    bo'lganda
    avtomatik ravishda konvertatsiya va
    previewga o'tkazadi.
    """

    try:
        elapsed = 0

        while elapsed < POLL_MAX_SECONDS:
            await asyncio.sleep(
                POLL_INTERVAL_SECONDS
            )

            elapsed += POLL_INTERVAL_SECONDS

            # Admin boshqa bosqichga o'tgan
            # yoki bekor qilgan bo'lsa,
            # bu eski poll vazifasini
            # jimgina to'xtatamiz.
            current_state = await state.get_state()

            if current_state != AddGameFSM.waiting_recording.state:
                return

            session = recording_bridge.get_session(
                token
            )

            if not session:
                return

            if session.status == "uploaded":
                await _finalize_uploaded_recording(
                    bot,
                    chat_id,
                    token,
                    state,
                )
                return

            if session.status == "error":
                error_text = (
                    session.error
                    or "noma'lum xato"
                )

                await bot.send_message(
                    chat_id,
                    f"❌ Video yozishda xato: {error_text}",
                )

                recording_bridge.pop_session(
                    token
                )
                return

        # Timeout
        await bot.send_message(
            chat_id,
            "⌛ <b>Video yozish vaqti tugadi.</b>\n\n"
            "🎬 MP4 YARATISH tugmasi orqali "
            "qaytadan urinib "
            "ko'ring yoki rasm/GIF "
            "yuboring.",
            parse_mode="HTML",
        )

        recording_bridge.pop_session(
            token
        )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "[RECORDING] Poll task crashed: "
            "token=%s",
            token,
        )

    finally:
        _ACTIVE_POLL_TASKS.pop(
            user_id,
            None,
        )


# =================================================
# RECORDING — MANUAL STATUS CHECK
# (FALLBACK)
# =================================================

@router.callback_query(
    F.data == "admin:recording_check",
    AddGameFSM.waiting_recording,
)
async def cb_recording_check(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    """
    🔄 Holatni tekshirish — fon vazifasi
    biror sababdan
    ishlamay qolgan taqdirda qo'lda
    tekshirish imkonini beradi.
    """

    data = await state.get_data()

    token = data.get(
        "recording_token"
    )

    if not token:
        await callback.answer(
            "❌ Session topilmadi.",
            show_alert=True,
        )
        return

    session = recording_bridge.get_session(
        token
    )

    if not session:
        await callback.answer(
            "❌ Session muddati tugagan. "
            "Qaytadan MP4 YARATISH "
            "tugmasini bosing.",
            show_alert=True,
        )
        return

    if session.status == "uploaded":
        await callback.answer(
            "✅ Video topildi, ishlanmoqda..."
        )

        await _finalize_uploaded_recording(
            bot,
            callback.message.chat.id,
            token,
            state,
        )
        return

    if session.status == "error":
        await callback.answer(
            f"❌ Xato: {session.error}",
            show_alert=True,
        )
        return

    await callback.answer(
        "⏳ Hali video yuborilmagan. "
        "O'ynab, 🎥 YOZISH / ⏹ TO'XTATISH "
        "tugmalarini bosing.",
        show_alert=True,
    )


# =================================================
# CONFIRM — SAQLASH
# =================================================

@router.callback_query(
    F.data == "admin:save",
    AddGameFSM.waiting_confirm,
)
async def cb_save(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    """
    ✅ Saqlash — HTML va thumbnailni webapp
    papkasiga yozadi,
    kerak bo'lsa GitHub'ga push qiladi va
    bazaga qo'shadi.
    """

    await callback.answer(
        "⏳ Saqlanmoqda..."
    )

    if not callback.message:
        return

    data = await state.get_data()

    slug = data.get("slug")
    name = data.get("name")
    description = data.get("description")
    category = data.get("category")
    html_file_id = data.get("html_file_id")

    image_kind = data.get(
        "image_kind",
        "photo",
    )

    if not (
        slug
        and name
        and description
        and category
        and html_file_id
    ):
        await callback.message.answer(
            "❌ Ma'lumotlar to'liq emas.\n\n"
            "Iltimos, /yangi jarayonini "
            "qaytadan boshlang."
        )
        return

    status = await callback.message.answer(
        "⏳ <b>Saqlanmoqda...</b>",
        parse_mode="HTML",
    )

    try:
        html_path = await save_html(
            bot,
            html_file_id,
            slug,
        )

        html_content = html_path.read_bytes()

        if image_kind == "mp4":
            image_path_str = data.get(
                "image_path"
            )

            if (
                not image_path_str
                or not Path(image_path_str).exists()
            ):
                raise RuntimeError(
                    "MP4 fayl topilmadi."
                )

            image_ext = ".mp4"

            image_content = Path(
                image_path_str
            ).read_bytes()

        else:
            image_file_id = data.get(
                "image_file_id"
            )

            image_ext = data.get(
                "image_ext",
                ".jpg",
            )

            if not image_file_id:
                raise RuntimeError(
                    "Thumbnail topilmadi."
                )

            image_path = await save_image(
                bot,
                image_file_id,
                slug,
                image_ext,
            )

            image_content = image

        await status.edit_text(
            "✅ <b>O'yin muvaffaqiyatli saqlandi!</b>\n\n"
            f"🎮 <b>{name}</b>\n"
            f"🔗 <code>{slug}</code>\n"
            f"🗂 {category}\n"
            f"🖼 Thumbnail: {image_ext}"
            f"{gh_status_line}",
            parse_mode="HTML",
        )

        logger.info(
            "[ADMIN] New game saved: "
            "slug=%s name=%s category=%s",
            slug,
            name,
            category,
        )

        # Recording session tugaganidan keyin
        # cleanup.
        if callback.from_user:
            _cleanup_admin_state(
                callback.from_user.id
            )

        await state.clear()

    except Exception as exc:
        logger.exception(
            "[ADMIN] Failed to save game: %s",
            exc,
        )

        await status.edit_text(
            "❌ <b>O'yinni saqlashda xato!</b>\n\n"
            f"<code>{str(exc)[:1000]}</code>",
            parse_mode="HTML",
        )


# =================================================
# CONFIRM — EDIT
# =================================================

@router.callback_query(
    F.data == "admin:edit",
    AddGameFSM.waiting_confirm,
)
async def cb_edit(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Previewdan keyin tahrirlash.
    Jarayon boshidan boshlanadi.
    """

    await callback.answer()

    if not callback.message:
        return

    data = await state.get_data()

    if callback.from_user:
        _cleanup_admin_state(
            callback.from_user.id
        )

    await _delete_orphan_html(
        data.get("slug")
    )

    await state.clear()

    await state.set_state(
        AddGameFSM.waiting_name
    )

    await callback.message.answer(
        "✏️ <b>Tahrirlash</b>\n\n"
        "1️⃣ O'yinning yangi "
        "<b>nomini</b> kiriting:\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )


# =================================================
# CONFIRM — CANCEL
# =================================================

@router.callback_query(
    F.data == "admin:cancel",
)
async def cb_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Inline ❌ Bekor tugmasi.
    """

    await callback.answer(
        "❌ Bekor qilindi."
    )

    if not callback.message:
        return

    data = await state.get_data()

    if callback.from_user:
        _cleanup_admin_state(
            callback.from_user.id
        )

    await _delete_orphan_html(
        data.get("slug")
    )

    await state.clear()

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.message.answer(
        "❌ Yangi o'yin qo'shish "
        "bekor qilindi."
    )


# =================================================
# FALLBACK — RECORDING MESSAGE
# =================================================

@router.message(
    AddGameFSM.waiting_recording
)
async def recording_message_fallback(
    message: Message,
) -> None:
    """
    Admin recording kutish bosqichida
    tasodifan matn/fayl yuborsa,
    unga nima qilish kerakligini
    tushuntiradi.
    """

    await message.answer(
        "🎬 Hozir MP4 yozib olinmoqda.\n\n"
        "▶️ <b>O'yinni ochish va yozish</b> "
        "tugmasini bosing.\n"
        "Keyin o'yin ichida:\n"
        "🎥 <b>YOZISH</b> → o'ynang → "
        "⏹ <b>TO'XTATISH</b>\n\n"
        "Video avtomatik ravishda botga "
        "yuboriladi.\n\n"
        "❌ Bekor qilish uchun /bekor "
        "buyrug'ini yuboring.",
        parse_mode="HTML",
    )


# =================================================
# FALLBACK — CONFIRM
# =================================================

@router.message(
    AddGameFSM.waiting_confirm
)
async def confirm_message_fallback(
    message: Message,
) -> None:
    """
    Preview bosqichida oddiy xabar yuborilsa,
    tugmalardan foydalanishni eslatadi.
    """

    await message.answer(
        "👇 Preview tayyor.\n\n"
        "✅ <b>Saqlash</b> — o'yinni saqlash\n"
        "✏️ <b>Tahrirlash</b> — qayta tahrirlash\n"
        "❌ <b>Bekor</b> — jarayonni bekor qilish",
        parse_mode="HTML",
    )