"""Admin-only /yangi handler.

Yangi o'yin qo'shish:
1. Nomi
2. Slug
3. Description
4. Category
5. HTML fayl
6. Thumbnail:
   - 🎬 MP4 YARATISH tugmasi
   - yoki oddiy rasm/GIF yuborish
7. Preview
8. Saqlash

MP4 rejimi:
- HTML o'yin vaqtinchalik brauzerda ochiladi
- avtomatik gameplay inputlari yuboriladi
- video yozib olinadi
- FFmpeg orqali MP4 hosil qilinadi
- MP4 thumbnail sifatida saqlanadi
"""

from __future__ import annotations

import asyncio
import io
import logging
import shutil
import tempfile
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

WEBAPP_DIR = Path(__file__).parent.parent / "webapp"


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
# Admin
# ─────────────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ─────────────────────────────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────────────────────────────

def _image_keyboard() -> InlineKeyboardMarkup:
    """Thumbnail bosqichidagi tugmalar."""

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
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor",
                    callback_data="admin:cancel",
                )
            ],
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Preview
# ─────────────────────────────────────────────────────────────────────────────

def _preview_caption(data: dict) -> str:
    media_kind = data.get("image_kind", "photo")

    if media_kind == "mp4":
        media_text = "🎬 MP4 avtomatik yaratildi"
    elif media_kind in {"animation", "gif_document"}:
        media_text = "🎞 GIF yuklandi"
    else:
        media_text = "🖼 Thumbnail yuklandi"

    return (
        f"🎮 <b>{data['name']}</b>\n\n"
        f"📝 {data['description']}\n\n"
        f"🗂 Kategoriya: <b>{data['category']}</b>\n"
        f"📄 HTML: <code>{data['slug']}.html</code>\n"
        f"{media_text}\n\n"
        "<i>Saqlashni tasdiqlaysizmi?</i>"
    )


async def _send_preview(
    message: Message,
    data: dict,
) -> None:
    """Yangi o'yinning preview kartasini yuboradi."""

    caption = _preview_caption(data)
    keyboard = _confirm_keyboard()

    image_id = data.get("image_file_id", "")
    image_kind = data.get("image_kind", "")

    # MP4
    if image_id and image_kind == "mp4":
        await message.answer_video(
            video=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
            supports_streaming=True,
        )
        return

    # Telegram GIF animation
    if image_id and image_kind == "animation":
        await message.answer_animation(
            animation=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # GIF document
    if image_id and image_kind == "gif_document":
        await message.answer_document(
            document=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # Normal image
    if image_id:
        await message.answer_photo(
            photo=image_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    await message.answer(
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Telegram file downloader
# ─────────────────────────────────────────────────────────────────────────────

async def _download_telegram_bytes(
    bot: Bot,
    file_id: str,
) -> bytes:
    """Telegram faylini xotiraga yuklaydi."""

    buffer = io.BytesIO()

    file_info = await bot.get_file(file_id)

    await bot.download_file(
        file_info.file_path,
        destination=buffer,
    )

    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# MP4 generator
# ─────────────────────────────────────────────────────────────────────────────

async def _create_mp4_from_html(
    html_bytes: bytes,
    slug: str,
) -> Path:
    """
    HTML o'yinni brauzerda ishga tushirib, gameplay videosini yaratadi.

    Natija:
        temporary_directory/{slug}.mp4
    """

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=f"game_preview_{slug}_"
        )
    )

    html_path = temp_dir / f"{slug}.html"
    video_dir = temp_dir / "video"

    video_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    html_path.write_bytes(html_bytes)

    try:
        # Playwright alohida import qilinadi.
        # Shu sababli MP4 funksiyasi ishlatilmaganda
        # oddiy /yangi ishlashiga xalaqit bermaydi.
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
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
                record_video_dir=str(video_dir),
                record_video_size={
                    "width": 640,
                    "height": 360,
                },
            )

            page = await context.new_page()

            # Local HTML.
            await page.goto(
                html_path.as_uri(),
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            # O'yin yuklanishi uchun vaqt.
            await page.wait_for_timeout(1_500)

            # O'yin maydonini fokuslash.
            try:
                await page.mouse.click(
                    320,
                    180,
                )
            except Exception:
                pass

            # Avtomatik gameplay.
            await _run_automatic_gameplay(page)

            # Oxirgi kadrlar yozilishi uchun biroz kutamiz.
            await page.wait_for_timeout(1_000)

            video_path = await page.video.path()

            await context.close()
            await browser.close()

        webm_path = Path(video_path)

        if not webm_path.exists():
            raise RuntimeError(
                "Brauzer video faylini yaratmadi."
            )

        mp4_path = temp_dir / f"{slug}.mp4"

        await _convert_video_to_mp4(
            webm_path,
            mp4_path,
        )

        if not mp4_path.exists():
            raise RuntimeError(
                "FFmpeg MP4 faylini yaratmadi."
            )

        logger.info(
            "[MP4] Created: slug=%s path=%s",
            slug,
            mp4_path,
        )

        return mp4_path

    except Exception:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True,
        )
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Automatic gameplay
# ─────────────────────────────────────────────────────────────────────────────

async def _run_automatic_gameplay(page) -> None:
    """
    Umumiy HTML o'yinlar uchun avtomatik inputlar.

    Bu universal AI player emas:
    - WASD
    - Arrow keys
    - Space
    - Enter
    - mouse click

    kabi keng tarqalgan o'yin boshqaruvlarini sinab ko'radi.
    """

    # 12 soniyalik gameplay.
    duration = 12.0
    interval = 0.35

    keys = [
        "ArrowRight",
        "ArrowRight",
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "Space",
        "ArrowRight",
        "ArrowDown",
        "ArrowRight",
        "Space",
        "d",
        "d",
        "a",
        "w",
        "s",
    ]

    start = asyncio.get_running_loop().time()
    index = 0

    while (
        asyncio.get_running_loop().time() - start
        < duration
    ):
        key = keys[index % len(keys)]
        index += 1

        try:
            await page.keyboard.down(key)
            await page.wait_for_timeout(120)
            await page.keyboard.up(key)
        except Exception:
            pass

        # Sichqoncha bilan ham harakat.
        try:
            x = 100 + ((index * 97) % 440)
            y = 100 + ((index * 53) % 180)

            await page.mouse.move(
                x,
                y,
                steps=3,
            )

            if index % 3 == 0:
                await page.mouse.click(
                    x,
                    y,
                )
        except Exception:
            pass

        await page.wait_for_timeout(
            int(interval * 1000)
        )

    # Ko'p o'yinlarda shooting / action uchun.
    for _ in range(8):
        try:
            await page.keyboard.press("Space")
        except Exception:
            pass

        await page.wait_for_timeout(250)


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg
# ─────────────────────────────────────────────────────────────────────────────

async def _convert_video_to_mp4(
    source: Path,
    destination: Path,
) -> None:
    """Playwright WebM videosini MP4 ga o'tkazadi."""

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(destination),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode(
            "utf-8",
            errors="ignore",
        )

        raise RuntimeError(
            f"FFmpeg xatosi: {error[-1500:]}"
        )


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
# Step 1 — Name
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


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Slug
# ─────────────────────────────────────────────────────────────────────────────

_SLUG_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_"
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

    if (
        not slug
        or not all(
            c in _SLUG_CHARS
            for c in slug
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

    existing = await get_game_by_slug(slug)

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


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Description
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
        "<i>arcade, puzzle, action, "
        "strategy, sport...</i>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Category
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
        "5️⃣ O'yinning <b>HTML faylini</b> "
        "document sifatida yuboring.\n\n"
        "📄 Faqat <code>.html</code> fayl.",
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
            "⚠️ HTML faylni "
            "<b>document</b> sifatida yuboring.",
            parse_mode="HTML",
        )
        return

    filename = doc.file_name or ""

    if not filename.lower().endswith(".html"):
        await message.answer(
            "⚠️ Faqat <code>.html</code> "
            "fayl qabul qilinadi.",
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
        "🎬 <b>MP4 YARATISH</b> tugmasini bossangiz "
        "bot HTML o'yinni avtomatik ishga tushirib, "
        "video yozadi va MP4 yaratadi.\n\n"
        "Yoki tugmani bosmasdan "
        "🖼 rasm / 🎞 GIF yuborishingiz mumkin.",
        reply_markup=_image_keyboard(),
        parse_mode="HTML",
    )
# ── Step 6 – thumbnail / MP4 ────────────────────────────────────────────────

@router.message(AddGameFSM.waiting_image)
async def step_image(message: Message, state: FSMContext) -> None:
    """
    Thumbnail bosqichi.

    Bu yerda:
      • 🎬 MP4 yaratish tugmasi ko'rsatiladi.
      • Admin tugmani bosmasa, oddiy rasm/GIF yuborishi mumkin.
      • Rasm/GIF yuborilsa — aynan o'sha media ishlatiladi.
      • MP4 tugmasi bosilsa — HTML o'yindan avtomatik video yaratish
        jarayoni boshlanadi.
    """

    file_id: str | None = None
    ext = ".jpg"
    image_kind = "photo"

    if message.photo:
        file_id = message.photo[-1].file_id
        ext = ".jpg"

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
                "⚠️ Faqat rasm fayllari qabul qilinadi:\n"
                "JPEG, PNG, GIF yoki WEBP.",
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
            "⚠️ Rasm yuboring yoki quyidagi tugmadan foydalaning.",
            reply_markup=_thumbnail_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.update_data(
        image_file_id=file_id,
        image_ext=ext,
        image_kind=image_kind,
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
        message.bot,
    )


# ── MP4 keyboard ────────────────────────────────────────────────────────────

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


# ── MP4 creation ────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:create_mp4",
    AddGameFSM.waiting_image,
)
async def cb_create_mp4(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    """
    HTML o'yindan avtomatik MP4 yaratishni boshlaydi.

    Muhim:
    MP4 yaratish alohida servis orqali bajariladi.
    admin.py faqat jarayonni boshqaradi.
    """

    await callback.answer(
        "🎬 MP4 yaratish boshlandi..."
    )

    data = await state.get_data()

    if not data.get("html_file_id"):
        await callback.message.answer(
            "❌ HTML fayl topilmadi."
        )
        return

    status = await callback.message.answer(
        "🎬 <b>MP4 tayyorlanmoqda...</b>\n\n"
        "🤖 O'yin avtomatik ishga tushiriladi.\n"
        "🎮 Bot o'yinni o'ynaydi.\n"
        "🎥 Jarayon yozib olinadi.\n\n"
        "⏳ Biroz kuting...",
        parse_mode="HTML",
    )

    try:
        # HTML faylni Telegram'dan olish
        html_bytes = await _download_telegram_bytes(
            bot,
            data["html_file_id"],
        )

        # MP4 generator servisini chaqirish
        from services.game_video_service import (
            create_game_mp4,
        )

        mp4_path = await create_game_mp4(
            slug=data["slug"],
            html_bytes=html_bytes,
        )

        if not mp4_path:
            raise RuntimeError(
                "MP4 generator fayl qaytarmadi."
            )

        # MP4 thumbnail sifatida saqlanadi
        mp4_bytes = mp4_path.read_bytes()

        save_image_bytes(
            data["slug"],
            ".mp4",
            mp4_bytes,
        )

        await state.update_data(
            image_file_id=None,
            image_ext=".mp4",
            image_kind="mp4",
            image_path=str(mp4_path),
        )

        await status.edit_text(
            "✅ <b>MP4 muvaffaqiyatli yaratildi!</b>\n\n"
            "🎬 Endi o'yin preview'ini tekshiring.",
            parse_mode="HTML",
        )

        await state.set_state(
            AddGameFSM.waiting_confirm
        )

        data = await state.get_data()

        await _send_preview(
            callback.message,
            data,
        )

    except Exception as exc:
        logger.exception(
            "Automatic MP4 creation failed: %s",
            exc,
        )

        await status.edit_text(
            "❌ <b>MP4 yaratishda xatolik</b>\n\n"
            f"<code>{str(exc)[:500]}</code>\n\n"
            "Rasm yoki GIF yuborib davom etishingiz mumkin.",
            parse_mode="HTML",
        )


# ── Thumbnail information ───────────────────────────────────────────────────

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
        "🎬 <b>MP4 YARATISH</b> — bot HTML o'yinni "
        "avtomatik ishga tushirib, o'yinchidek o'ynaydi "
        "va video yozadi.\n\n"
        "🖼 <b>Rasm/GIF</b> — o'zingiz tayyor rasm yoki "
        "GIF yuborasiz.\n\n"
        "Hech narsa avtomatik boshlanmaydi. "
        "MP4 faqat tugma bosilganda yaratiladi.",
        reply_markup=_thumbnail_keyboard(),
        parse_mode="HTML",
    )


# ── Step 7 – Confirm callbacks ──────────────────────────────────────────────

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

    slug = data["slug"]

    try:
        # HTML
        html_bytes = await _download_telegram_bytes(
            bot,
            data["html_file_id"],
        )

        save_html_bytes(
            slug,
            html_bytes,
        )

        # Thumbnail
        image_kind = data.get("image_kind")

        if image_kind == "mp4":
            mp4_path = data.get("image_path")

            if not mp4_path:
                raise RuntimeError(
                    "MP4 fayl yo'li topilmadi."
                )

            image_bytes = Path(
                mp4_path
            ).read_bytes()

            image_ext = ".mp4"

            image_path = save_image_bytes(
                slug,
                image_ext,
                image_bytes,
            )

        else:
            image_bytes = await _download_telegram_bytes(
                bot,
                data["image_file_id"],
            )

            image_ext = data["image_ext"]

            image_path = save_image_bytes(
                slug,
                image_ext,
                image_bytes,
            )

        # Database
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

        # GitHub
        gh_status_line = ""

        if config.AUTO_GITHUB_PUSH:
            from services.github_service import (
                push_game_files,
            )

            gh_ok, gh_msg = await push_game_files(
                slug,
                html_bytes,
                image_bytes,
                image_path.suffix,
            )

            if gh_ok:
                gh_status_line = (
                    "\n🐙 GitHub: ✅ push qilindi"
                )
            else:
                gh_status_line = (
                    "\n🐙 GitHub: ⚠️ push amalga oshmadi"
                )

                await callback.message.answer(
                    "⚠️ <b>GitHub push xatosi</b>\n\n"
                    "O'yin saqlandi, lekin GitHub'ga "
                    "push qilinmadi.\n\n"
                    f"<code>{gh_msg[:300]}</code>",
                    parse_mode="HTML",
                )

        else:
            logger.info(
                "[GITHUB] AUTO_GITHUB_PUSH=False"
            )

        await state.clear()

        # Confirmation buttons
        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        media_label = (
            "🎬 MP4 avtomatik yaratildi"
            if image_kind == "mp4"
            else "🖼 Thumbnail yuklandi"
        )

        await callback.message.answer(
            "✅ <b>O'yin muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🆔 Slug: <code>{game['slug']}</code>\n"
            f"📛 Nomi: <b>{game['name']}</b>\n"
            f"📝 Ta'rif: {game['description']}\n"
            f"🗂 Kategoriya: {game['category']}\n"
            f"📄 HTML: <code>{game['html_file']}</code>\n"
            f"{media_label}"
            f"{gh_status_line}\n\n"
            f"Hoziroq ko'rish: "
            f"/oyinlar {game['slug']}",
            parse_mode="HTML",
        )

        # Live game card
        from services.game_service import (
            send_game_card,
        )

        await send_game_card(
            callback.message,
            game,
        )

        logger.info(
            "Admin saved game: slug=%s mp4=%s",
            slug,
            image_kind == "mp4",
        )

    except Exception as exc:
        logger.exception(
            "Failed to save game slug=%s",
            slug,
        )

        await callback.message.answer(
            "❌ <b>O'yinni saqlashda xato</b>\n\n"
            f"<code>{str(exc)[:500]}</code>",
            parse_mode="HTML",
        )


# ── Edit ─────────────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:edit",
    AddGameFSM.waiting_confirm,
)
async def cb_edit(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await callback.answer(
        "✏️ Qayta boshlash..."
    )

    await state.clear()

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "🔄 <b>Jarayon qayta boshlandi.</b>\n\n"
        "1️⃣ O'yinning <b>ko'rinadigan nomi</b>ni kiriting:\n"
        "<i>Masalan: 🐍 Ilon O'yini</i>\n\n"
        "/bekor — bekor qilish",
        parse_mode="HTML",
    )

    await state.set_state(
        AddGameFSM.waiting_name
    )


# ── Cancel ───────────────────────────────────────────────────────────────────

@router.callback_query(
    F.data == "admin:cancel",
)
async def cb_cancel_confirm(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await callback.answer(
        "❌ Bekor qilindi."
    )

    await state.clear()

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.message.answer(
        "❌ <b>O'yin qo'shish bekor qilindi.</b>",
        parse_mode="HTML",
    )