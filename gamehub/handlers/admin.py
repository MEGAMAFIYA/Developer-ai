"""Admin-only handler: /yangi — upload a new game via FSM.

Steps
-----
1. Game name
2. Slug
3. Description
4. Category
5. Upload HTML game
6. Thumbnail:
   - 🎬 MP4 YARATISH
   - OR upload photo / GIF / image document
7. Preview → Save / Edit / Cancel
"""

import io
import logging

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
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


# ─────────────────────────────────────────────────────────────────────────────
# FSM
# ─────────────────────────────────────────────────────────────────────────────

class AddGameFSM(StatesGroup):
    waiting_name = State()
    waiting_slug = State()
    waiting_description = State()
    waiting_category = State()
    waiting_html = State()
    waiting_image = State()
    waiting_confirm = State()


# ─────────────────────────────────────────────────────────────────────────────
# Guards
# ─────────────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _image_choice_keyboard() -> InlineKeyboardMarkup:
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
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )


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
                InlineKeyboardButton(
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                ),
            ]
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Preview
# ─────────────────────────────────────────────────────────────────────────────

def _preview_caption(data: dict) -> str:
    media_type = data.get("image_kind", "photo")

    if media_type == "mp4":
        media_line = "🎬 MP4: <b>avtomatik yaratildi</b>"
    elif media_type == "animation":
        media_line = "🎞 GIF: <b>yuklandi</b>"
    elif media_type == "document":
        media_line = "🖼 Rasm: <b>yuklandi</b>"
    else:
        media_line = "🖼 Rasm: <b>yuklandi</b>"

    return (
        f"🎮 <b>{data['name']}</b>\n\n"
        f"📝 {data['description']}\n\n"
        f"🗂 Kategoriya: <b>{data['category']}</b>\n"
        f"📄 HTML: <code>{data['slug']}.html</code>\n"
        f"{media_line}\n\n"
        "<i>Saqlashni tasdiqlaysizmi?</i>"
    )


async def _send_preview(
    message: Message,
    data: dict,
    bot: Bot,
) -> None:
    """Send thumbnail/MP4 preview with confirmation buttons."""

    caption = _preview_caption(data)
    keyboard = _confirm_keyboard()

    image_id = data.get("image_file_id")

    if not image_id:
        await message.answer(
            caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    kind = data.get("image_kind")

    if kind == "animation":
        await message.answer_animation(
            animation=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    if kind == "gif_document":
        await message.answer_document(
            document=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    if kind == "mp4":
        await message.answer_video(
            video=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
            supports_streaming=True,
        )
        return

    await message.answer_photo(
        photo=image_id,
        caption=caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _download_telegram_bytes(
    bot: Bot,
    file_id: str,
) -> bytes:
    buffer = io.BytesIO()

    file_info = await bot.get_file(file_id)

    await bot.download_file(
        file_info.file_path,
        destination=buffer,
    )

    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# /yangi
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("yangi"))
async def cmd_yangi(
    message: Message,
    state: FSMContext,
) -> None:

    if not _is_admin(message.from_user.id):
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
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# /bekor
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("bekor"))
async def cmd_cancel(
    message: Message,
    state: FSMContext,
) -> None:

    if await state.get_state() is None:
        return

    await state.clear()

    await message.answer(
        "❌ Jarayon bekor qilindi."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — name
# ─────────────────────────────────────────────────────────────────────────────

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
            "⚠️ Nom kamida 2 ta belgidan iborat bo'lishi kerak."
        )
        return

    await state.update_data(name=name)

    await state.set_state(
        AddGameFSM.waiting_slug
    )

    await message.answer(
        f"✅ Nomi: <b>{name}</b>\n\n"
        "2️⃣ <b>Slug</b> kiriting:\n"
        "<i>Masalan: zombi, ilon-oyini, space-shooter</i>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — slug
# ─────────────────────────────────────────────────────────────────────────────

_SLUG_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz0123456789-_"
)


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

    slug = message.text.strip().lower()

    if not slug or not all(
        c in _SLUG_CHARS
        for c in slug
    ):
        await message.answer(
            "⚠️ Slug faqat kichik lotin harflar, "
            "raqamlar, <code>-</code> yoki <code>_</code>.",
            parse_mode="HTML",
        )
        return

    existing = await get_game_by_slug(slug)

    if existing:
        await message.answer(
            f"⚠️ <code>{slug}</code> slugli o'yin "
            "allaqachon mavjud.",
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
        "3️⃣ O'yin haqida qisqa <b>ta'rif</b> kiriting:",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — description
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_description)
async def step_description(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn kiriting."
        )
        return

    await state.update_data(
        description=message.text.strip()
    )

    await state.set_state(
        AddGameFSM.waiting_category
    )

    await message.answer(
        "4️⃣ <b>Kategoriya</b>ni kiriting:\n"
        "<i>arcade, puzzle, action, strategy, sport...</i>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — category
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_category)
async def step_category(
    message: Message,
    state: FSMContext,
) -> None:

    if not message.text:
        await message.answer(
            "⚠️ Iltimos, matn kiriting."
        )
        return

    category = message.text.strip().lower()

    await state.update_data(
        category=category
    )

    await state.set_state(
        AddGameFSM.waiting_html
    )

    await message.answer(
        f"✅ Kategoriya: <b>{category}</b>\n\n"
        "5️⃣ O'yin <b>HTML faylini</b> yuboring.\n"
        "<i>Faqat .html document.</i>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — HTML
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_html)
async def step_html(
    message: Message,
    state: FSMContext,
) -> None:

    doc = message.document

    if not doc:
        await message.answer(
            "⚠️ HTML faylni document sifatida yuboring.",
            parse_mode="HTML",
        )
        return

    filename = doc.file_name or ""

    if not filename.lower().endswith(".html"):
        await message.answer(
            "⚠️ Faqat <code>.html</code> fayl qabul qilinadi.",
            parse_mode="HTML",
        )
        return

    await state.update_data(
        html_file_id=doc.file_id,
        html_orig_name=filename,
    )

    await state.set_state(
        AddGameFSM.waiting_image
    )

    await message.answer(
        f"✅ HTML qabul qilindi: "
        f"<code>{filename}</code>\n\n"
        "6️⃣ <b>Thumbnail</b> tanlang:\n\n"
        "🎬 <b>MP4 YARATISH</b> — bot o'yinni avtomatik "
        "ishga tushirib, o'ynayotgandek yozib oladi.\n\n"
        "Yoki shunchaki <b>rasm / GIF / image document</b> yuboring.",
        reply_markup=_image_choice_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 6A — Generate MP4
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:create_mp4",
    AddGameFSM.waiting_image,
)
async def cb_create_mp4(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:

    await callback.answer(
        "🎬 MP4 tayyorlanmoqda..."
    )

    data = await state.get_data()

    html_file_id = data.get("html_file_id")
    slug = data.get("slug")

    if not html_file_id or not slug:
        await callback.message.answer(
            "❌ HTML fayl topilmadi. /yangi ni qaytadan boshlang."
        )
        return

    status_message = await callback.message.answer(
        "🎬 <b>MP4 yaratilmoqda...</b>\n\n"
        "🌐 O'yin brauzerda ishga tushirilmoqda...\n"
        "🎮 Avtomatik o'yin boshqaruvi ishga tushadi...\n"
        "📹 Ekran yozib olinmoqda...\n\n"
        "⏳ Bir oz kuting...",
        parse_mode="HTML",
    )

    try:
        html_bytes = await _download_telegram_bytes(
            bot,
            html_file_id,
        )

        # The actual browser/game recorder lives separately.
        from services.video_service import (
            generate_game_mp4,
        )

        result = await generate_game_mp4(
            slug=slug,
            html_bytes=html_bytes,
        )

        if not result:
            raise RuntimeError(
                "MP4 generator bo'sh natija qaytardi."
            )

        # Upload generated MP4 back to Telegram.
        from aiogram.types import FSInputFile

        video_message = await callback.message.answer_video(
            video=FSInputFile(str(result)),
            caption=(
                "🎬 <b>MP4 tayyor!</b>\n\n"
                "Bu video o'yinning avtomatik "
                "o'ynalishi asosida yaratildi."
            ),
            supports_streaming=True,
            parse_mode="HTML",
        )

        # Telegram file_id becomes our thumbnail/media source.
        video_file_id = video_message.video.file_id

        await state.update_data(
            image_file_id=video_file_id,
            image_ext=".mp4",
            image_kind="mp4",
            image_source="generated",
        )

        await callback.message.edit_text(
            "✅ <b>MP4 muvaffaqiyatli yaratildi!</b>\n\n"
            "Endi o'yin kartasi preview qilinmoqda...",
            parse_mode="HTML",
        )

        await state.set_state(
            AddGameFSM.waiting_confirm
        )

        data = await state.get_data()

        await _send_preview(
            callback.message,
            data,
            bot,
        )

    except Exception as exc:
        logger.exception(
            "MP4 generation failed: slug=%s",
            slug,
        )

        await callback.message.answer(
            "❌ <b>MP4 yaratishda xato</b>\n\n"
            f"<code>{str(exc)[:1000]}</code>\n\n"
            "Rasm yoki GIF yuborib davom etishingiz mumkin.",
            parse_mode="HTML",
        )

    finally:
        try:
            if result:
                result.unlink(missing_ok=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Step 6B — Upload normal image/GIF
# ─────────────────────────────────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_image)
async def step_image(
    message: Message,
    state: FSMContext,
) -> None:

    file_id: str | None = None
    ext = ".jpg"
    image_kind = "photo"

    if message.photo:

        file_id = message.photo[-1].file_id
        ext = ".jpg"
        image_kind = "photo"

    elif message.animation:

        file_id = message.animation.file_id
        ext = ".gif"
        image_kind = "animation"

    elif message.document:

        doc = message.document

        ext = image_ext_from_filename_or_mime(
            doc.file_name,
            doc.mime_type,
        )

        if ext is None:
            await message.answer(
                "⚠️ Faqat JPEG, PNG, GIF yoki WEBP "
                "rasm fayllari qabul qilinadi.",
                parse_mode="HTML",
            )
            return

        file_id = doc.file_id

        image_kind = (
            "gif_document"
            if ext == ".gif"
            else "document"
        )

    else:

        await message.answer(
            "⚠️ Rasm/GIF yuboring yoki "
            "🎬 MP4 YARATISH tugmasini bosing.",
            reply_markup=_image_choice_keyboard(),
        )
        return

    await state.update_data(
        image_file_id=file_id,
        image_ext=ext,
        image_kind=image_kind,
        image_source="uploaded",
    )

    await state.set_state(
        AddGameFSM.waiting_confirm
    )

    data = await state.get_data()

    await message.answer(
        "✅ Media qabul qilindi! Tekshirib ko'ring 👇"
    )

    await _send_preview(
        message,
        data,
        message.bot,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Save
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:save",
    AddGameFSM.waiting_confirm,
)
async def cb_save(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:

    await callback.answer(
        "⏳ Saqlanmoqda..."
    )

    data = await state.get_data()

    await state.clear()

    slug = data["slug"]
    image_ext = data["image_ext"]

    try:

        html_bytes = await _download_telegram_bytes(
            bot,
            data["html_file_id"],
        )

        image_file_id = data["image_file_id"]

        # MP4 generated by the browser recorder is already
        # stored in Telegram, therefore download it back
        # just like a normal uploaded media file.
        image_bytes = await _download_telegram_bytes(
            bot,
            image_file_id,
        )

        save_html_bytes(
            slug,
            html_bytes,
        )

        image_path = save_image_bytes(
            slug,
            image_ext,
            image_bytes,
        )

        img_url = image_db_url(
            slug,
            image_path.suffix,
        )

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

        # ─────────────────────────────────────────────────────────
        # GitHub auto-push
        gh_status_line = ""

        if config.AUTO_GITHUB_PUSH:
            from services.github_service import push_game_files

            gh_ok, gh_msg = await push_game_files(
                slug,
                html_bytes,
                image_bytes,
                image_path.suffix,
            )

            if gh_ok:
                logger.info(
                    "GitHub push OK: slug=%s | %s",
                    slug,
                    gh_msg,
                )
                gh_status_line = "\n🐙 GitHub: ✅ push qilindi"
            else:
                logger.error(
                    "GitHub push FAILED: slug=%s | %s",
                    slug,
                    gh_msg,
                )
                gh_status_line = (
                    "\n🐙 GitHub: ⚠️ push amalga oshmadi"
                )

                await callback.message.answer(
                    "⚠️ <b>GitHub push xatosi</b>\n\n"
                    "O'yin saqlandi, lekin GitHub'ga push qilinmadi.\n\n"
                    f"<code>{gh_msg[:300]}</code>",
                    parse_mode="HTML",
                )
        else:
            logger.info(
                "[GITHUB] AUTO_GITHUB_PUSH=False — push o'tkazib yuborildi"
            )

        # Confirmation tugmalarini olib tashlash
        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        media_label = (
            "🎬 MP4 avtomatik yaratildi"
            if data.get("image_kind") == "mp4"
            else "🖼 Thumbnail yuklandi"
        )

        await callback.message.answer(
            "✅ <b>O'yin muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🆔 Slug: <code>{game['slug']}</code>\n"
            f"📛 Nomi: <b>{game['name']}</b>\n"
            f"📝 Ta'rif: {game['description']}\n"
            f"🗂 Kategoriya: {game['category']}\n"
            f"📄 HTML: <code>{game['html_file']}</code>\n"
            f"🎬 Media: {media_label}\n"
            f"{gh_status_line}\n\n"
            f"Hoziroq ko'rish: /oyinlar {game['slug']}",
            parse_mode="HTML",
        )

        # Foydalanuvchilarga ko'rinadigan game card
        from services.game_service import send_game_card

        await send_game_card(
            callback.message,
            game,
        )

        logger.info(
            "Admin saved new game: slug=%s auto_github_push=%s",
            slug,
            config.AUTO_GITHUB_PUSH,
        )

    except Exception:
        logger.exception(
            "Failed to save game slug=%s",
            slug,
        )

        await callback.message.answer(
            "❌ Xato yuz berdi. Qayta urinib ko'ring: /yangi"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tahrirlash
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:edit",
    AddGameFSM.waiting_confirm,
)
async def cb_edit(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await callback.answer("✏️ Qayta boshlash...")
    await state.clear()

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "🔄 Jarayon qayta boshlandi.\n\n"
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )

    await state.set_state(
        AddGameFSM.waiting_name
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bekor qilish
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:cancel",
    AddGameFSM.waiting_confirm,
)
async def cb_cancel_confirm(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await callback.answer("❌ Bekor qilindi.")
    await state.clear()

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "❌ O'yin qo'shish bekor qilindi."
    )