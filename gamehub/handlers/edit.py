"""Admin-only handler: /tuzatish — edit an existing game via 7-step FSM wizard.

Steps (each shows current value + ✅ O'tkazish / ❌ Bekor qilish buttons):
  1. Name          — free text
  2. Description   — free text
  3. Cover image   — photo or image document
  4. HTML file     — .html document  (slug stays the same, links unchanged)
  5. Category      — free text
  6. Tags          — comma-separated free text
  7. Visibility    — inline buttons: 🌍 Ommaviy | 🔒 Yopiq
  → Confirm card  — ✅ Saqlash | ✏️ Yana tahrirlash | ❌ Bekor qilish
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
    FSInputFile,
)

from config import config
from database.global_db import get_all_games, get_game_by_slug, update_game
from services.upload_service import (
    save_html, save_image, ext_from_mime, image_db_url, WEBAPP_DIR,
)

logger = logging.getLogger(__name__)
router = Router()

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}


# ── FSM States ────────────────────────────────────────────────────────────────

class EditGameFSM(StatesGroup):
    waiting_name        = State()   # 1 – display name
    waiting_description = State()   # 2 – description
    waiting_image       = State()   # 3 – cover image
    waiting_html        = State()   # 4 – HTML file
    waiting_category    = State()   # 5 – category
    waiting_tags        = State()   # 6 – tags
    waiting_visibility  = State()   # 7 – public / private
    waiting_confirm     = State()   # preview + save


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ O'tkazish",    callback_data="edit:skip"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="edit:cancel"),
    ]])


def _visibility_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌍 Ommaviy", callback_data="edit:vis:public"),
            InlineKeyboardButton(text="🔒 Yopiq",   callback_data="edit:vis:private"),
        ],
        [
            InlineKeyboardButton(text="✅ O'tkazish",    callback_data="edit:skip"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="edit:cancel"),
        ],
    ])


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Saqlash",         callback_data="edit:save"),
        InlineKeyboardButton(text="✏️ Yana tahrirlash", callback_data="edit:restart"),
        InlineKeyboardButton(text="❌ Bekor qilish",    callback_data="edit:cancel"),
    ]])


# ── Step prompt senders ───────────────────────────────────────────────────────
# Each _ask_* sets the FSM state and sends the prompt.
# `target` is always a Message (either message or callback.message).

async def _ask_name(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(EditGameFSM.waiting_name)
    await target.answer(
        f"1️⃣ <b>Nomi</b>\n\n"
        f"Hozirgi qiymat: <b>{data['edit_name']}</b>\n\n"
        "Yangi nom yuboring yoki o'tkazib yuboring:",
        parse_mode="HTML",
        reply_markup=_skip_kb(),
    )


async def _ask_description(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(EditGameFSM.waiting_description)
    await target.answer(
        f"2️⃣ <b>Ta'rif</b>\n\n"
        f"Hozirgi qiymat:\n<i>{data['edit_description']}</i>\n\n"
        "Yangi ta'rif yuboring yoki o'tkazib yuboring:",
        parse_mode="HTML",
        reply_markup=_skip_kb(),
    )


async def _ask_image(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    img = data.get("edit_image_url") or "(yo'q)"
    await state.set_state(EditGameFSM.waiting_image)
    await target.answer(
        f"3️⃣ <b>Muqova rasmi</b>\n\n"
        f"Hozirgi rasm: <code>{img}</code>\n\n"
        "Yangi rasm yuboring (foto yoki rasm fayli)\n"
        "yoki o'tkazib yuboring:",
        parse_mode="HTML",
        reply_markup=_skip_kb(),
    )


async def _ask_html(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(EditGameFSM.waiting_html)
    await target.answer(
        f"4️⃣ <b>HTML fayli</b>\n\n"
        f"Hozirgi fayl: <code>{data['edit_html_file']}</code>\n\n"
        "Yangi HTML faylni yuboring yoki o'tkazib yuboring:\n"
        "<i>Slug o'zgarmaydi — mavjud havolalar ishlashda davom etadi.</i>",
        parse_mode="HTML",
        reply_markup=_skip_kb(),
    )


async def _ask_category(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(EditGameFSM.waiting_category)
    await target.answer(
        f"5️⃣ <b>Kategoriya</b>\n\n"
        f"Hozirgi qiymat: <code>{data['edit_category']}</code>\n\n"
        "Yangi kategoriya yuboring yoki o'tkazib yuboring:\n"
        "<i>Masalan: arcade, puzzle, action, strategy, sport</i>",
        parse_mode="HTML",
        reply_markup=_skip_kb(),
    )


async def _ask_tags(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tags = data.get("edit_tags") or "(yo'q)"
    await state.set_state(EditGameFSM.waiting_tags)
    await target.answer(
        f"6️⃣ <b>Teglar (tags)</b>\n\n"
        f"Hozirgi qiymat: <code>{tags}</code>\n\n"
        "Yangi teglar yuboring (vergul bilan ajrating)\n"
        "yoki o'tkazib yuboring:\n"
        "<i>Masalan: klassik, qiziqarli, yakkabosh</i>",
        parse_mode="HTML",
        reply_markup=_skip_kb(),
    )


async def _ask_visibility(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    current = "🌍 Ommaviy" if data.get("edit_active", True) else "🔒 Yopiq"
    await state.set_state(EditGameFSM.waiting_visibility)
    await target.answer(
        f"7️⃣ <b>Ko'rinish (visibility)</b>\n\n"
        f"Hozirgi holat: {current}\n\n"
        "Yangi holat tanlang yoki o'tkazib yuboring:",
        parse_mode="HTML",
        reply_markup=_visibility_kb(),
    )


async def _ask_confirm(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(EditGameFSM.waiting_confirm)

    active_str = "🌍 Ommaviy" if data.get("edit_active", True) else "🔒 Yopiq"
    tags_str   = data.get("edit_tags") or "—"

    caption = (
        "📋 <b>O'zgartirishlarni tasdiqlang</b>\n\n"
        f"🆔 Slug: <code>{data['slug']}</code>\n"
        f"📛 Nomi: <b>{data['edit_name']}</b>\n"
        f"📝 Ta'rif: {data['edit_description']}\n"
        f"🗂 Kategoriya: <code>{data['edit_category']}</code>\n"
        f"🏷 Teglar: <code>{tags_str}</code>\n"
        f"📄 HTML: <code>{data['edit_html_file']}</code>\n"
        f"👁 Ko'rinish: {active_str}\n\n"
        "<i>Saqlashni tasdiqlaysizmi?</i>"
    )
    kb = _confirm_kb()

    # Prefer new image file_id → then existing local file → text fallback
    new_fid = data.get("edit_image_file_id")
    if new_fid:
        await target.answer_photo(
            photo=new_fid, caption=caption, reply_markup=kb, parse_mode="HTML",
        )
        return

    orig_url = data.get("edit_image_url", "")
    if orig_url.startswith("/webapp/"):
        fp = WEBAPP_DIR / orig_url.removeprefix("/webapp/")
        if fp.exists():
            try:
                await target.answer_photo(
                    photo=FSInputFile(str(fp)),
                    caption=caption, reply_markup=kb, parse_mode="HTML",
                )
                return
            except Exception as exc:
                logger.warning("Preview photo failed: %s", exc)

    await target.answer(caption, reply_markup=kb, parse_mode="HTML")


# ── Step → next-step map (populated after function definitions) ───────────────
# Filled at module bottom to avoid forward-reference issues.
_NEXT_STEP: dict = {}


# ── /tuzatish command ─────────────────────────────────────────────────────────

@router.message(Command("tuzatish"))
async def cmd_tuzatish(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    await state.clear()
    games = await get_all_games(only_active=False)

    if not games:
        await message.answer("😔 Hali hech qanday o'yin qo'shilmagan.")
        return

    # Build 2-column button grid
    # callback_data = "eg:{slug}" (prefix 3 chars; slug ≤ 61 chars safe)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for g in games:
        status = "✅" if g["active"] else "🔒"
        row.append(InlineKeyboardButton(
            text=f"{status} {g['name']}",
            callback_data=f"eg:{g['slug']}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    await message.answer(
        "✏️ <b>Qaysi o'yinni tahrirlash kerak?</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ── Game selection callback ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("eg:"))
async def cb_select_game(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q!", show_alert=True)
        return

    slug = callback.data[3:]          # strip "eg:" prefix
    game = await get_game_by_slug(slug)
    if not game:
        await callback.answer("❌ O'yin topilmadi!", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    # Seed FSM data: all edit_* values start from the current DB row
    await state.set_data({
        "slug":               game["slug"],
        "orig_image_url":     game.get("image_url", ""),
        # Working values — modified step by step
        "edit_name":          game["name"],
        "edit_description":   game["description"],
        "edit_image_url":     game.get("image_url", ""),
        "edit_image_file_id": None,
        "edit_image_ext":     None,
        "edit_html_file":     game.get("html_file", f"{game['slug']}.html"),
        "edit_html_file_id":  None,
        "edit_category":      game.get("category", "arcade"),
        "edit_tags":          game.get("tags", ""),
        "edit_active":        game.get("active", True),
    })

    await callback.message.answer(
        f"✏️ <b>{game['name']}</b> o'yinini tahrirlash boshlandi.\n\n"
        "Har bir qadam uchun yangi qiymat yuboring yoki\n"
        "<b>✅ O'tkazish</b> — hozirgi qiymatni saqlash.",
        parse_mode="HTML",
    )
    await _ask_name(callback.message, state)


# ── Step 1: Name ──────────────────────────────────────────────────────────────

@router.message(EditGameFSM.waiting_name)
async def step_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Nom kamida 2 ta belgidan iborat bo'lishi kerak.")
        return
    await state.update_data(edit_name=name)
    await _ask_description(message, state)


# ── Step 2: Description ───────────────────────────────────────────────────────

@router.message(EditGameFSM.waiting_description)
async def step_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    await state.update_data(edit_description=message.text.strip())
    await _ask_image(message, state)


# ── Step 3: Cover image ───────────────────────────────────────────────────────

@router.message(EditGameFSM.waiting_image)
async def step_image(message: Message, state: FSMContext) -> None:
    file_id: str | None = None
    ext = ".jpg"

    if message.photo:
        file_id = message.photo[-1].file_id

    elif message.document:
        doc  = message.document
        mime = doc.mime_type or ""
        if mime not in ALLOWED_IMAGE_MIME:
            await message.answer(
                "⚠️ Faqat rasm fayllari qabul qilinadi (JPEG, PNG, GIF, WEBP)."
            )
            return
        file_id = doc.file_id
        suffix  = Path(doc.file_name or "").suffix.lower()
        ext = suffix if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"} \
            else ext_from_mime(mime)
        if ext == ".jpeg":
            ext = ".jpg"

    else:
        await message.answer(
            "⚠️ Iltimos, rasmni foto yoki rasm fayli sifatida yuboring.",
            reply_markup=_skip_kb(),
        )
        return

    await state.update_data(edit_image_file_id=file_id, edit_image_ext=ext)
    await _ask_html(message, state)


# ── Step 4: HTML file ─────────────────────────────────────────────────────────

@router.message(EditGameFSM.waiting_html)
async def step_html(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not doc:
        await message.answer(
            "⚠️ Iltimos, HTML faylni <b>fayl (document)</b> sifatida yuboring.",
            parse_mode="HTML",
            reply_markup=_skip_kb(),
        )
        return
    if not (doc.file_name or "").lower().endswith(".html"):
        await message.answer(
            "⚠️ Faqat <code>.html</code> kengaytmali fayl qabul qilinadi.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    await state.update_data(
        edit_html_file_id=doc.file_id,
        edit_html_file=f"{data['slug']}.html",   # always slug-named
    )
    await _ask_category(message, state)


# ── Step 5: Category ──────────────────────────────────────────────────────────

@router.message(EditGameFSM.waiting_category)
async def step_category(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    await state.update_data(edit_category=message.text.strip().lower())
    await _ask_tags(message, state)


# ── Step 6: Tags ──────────────────────────────────────────────────────────────

@router.message(EditGameFSM.waiting_tags)
async def step_tags(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("⚠️ Iltimos, matn kiriting.")
        return
    await state.update_data(edit_tags=message.text.strip())
    await _ask_visibility(message, state)


# ── Step 7: Visibility — inline buttons only ──────────────────────────────────

@router.callback_query(
    F.data.in_({"edit:vis:public", "edit:vis:private"}),
    EditGameFSM.waiting_visibility,
)
async def cb_visibility(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_active=(callback.data == "edit:vis:public"))
    await callback.answer()
    await _ask_confirm(callback.message, state)


@router.message(EditGameFSM.waiting_visibility)
async def step_visibility_text(message: Message) -> None:
    """Guard: nudge user to use buttons instead of typing."""
    await message.answer(
        "⚠️ Iltimos, quyidagi tugmalardan birini tanlang:",
        reply_markup=_visibility_kb(),
    )


# ── Confirm step: ignore stray messages ───────────────────────────────────────

@router.message(EditGameFSM.waiting_confirm)
async def step_confirm_text(message: Message) -> None:
    await message.answer(
        "⚠️ Tasdiqlash uchun quyidagi tugmalardan foydalaning:",
        reply_markup=_confirm_kb(),
    )


# ── Shared callback: O'tkazish (skip current step) ────────────────────────────

@router.callback_query(F.data == "edit:skip")
async def cb_skip(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    next_fn = _NEXT_STEP.get(current)
    if next_fn is None:
        await callback.answer("⚠️ Noto'g'ri holat", show_alert=True)
        return
    await callback.answer("✅ O'tkazildi")
    await next_fn(callback.message, state)


# ── Shared callback: Bekor qilish ─────────────────────────────────────────────

@router.callback_query(F.data == "edit:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("❌ Bekor qilindi")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("❌ Tahrirlash bekor qilindi.")


# ── Confirm: Saqlash ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "edit:save", EditGameFSM.waiting_confirm)
async def cb_save(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer("⏳ Saqlanmoqda...")
    data = await state.get_data()
    await state.clear()

    slug      = data["slug"]
    image_url = data["edit_image_url"]   # may be updated below

    try:
        # 1. Replace HTML on disk if a new file was uploaded
        gh_status_line = ""
        if data.get("edit_html_file_id"):
            html_path = await save_html(bot, data["edit_html_file_id"], slug)
            logger.info("Replaced HTML for slug=%s", slug)

            # Match /yangi: keep the runtime save, then persist the same HTML
            # through the shared GitHub project provider when enabled.
            if config.AUTO_GITHUB_PUSH:
                from services.github_service import push_game_html

                gh_ok, gh_msg = await push_game_html(slug, html_path.read_bytes())
                if gh_ok:
                    logger.info("GitHub HTML update OK: slug=%s | %s", slug, gh_msg)
                    gh_status_line = "\n🐙 GitHub: ✅ HTML push qilindi"
                else:
                    logger.error("GitHub HTML update FAILED: slug=%s | %s", slug, gh_msg)
                    gh_status_line = "\n🐙 GitHub: ⚠️ HTML push amalga oshmadi (o'yin saqlandi)"
                    await callback.message.answer(
                        f"⚠️ <b>GitHub HTML push xatosi</b>\n\n"
                        f"O'yin muvaffaqiyatli saqlandi, lekin HTML GitHub'ga push qilinmadi.\n\n"
                        f"<code>{gh_msg[:300]}</code>",
                        parse_mode="HTML",
                    )
            else:
                logger.info("[GITHUB] AUTO_GITHUB_PUSH=False — HTML push o'tkazib yuborildi")

        # 2. Replace image on disk if a new image was uploaded
        if data.get("edit_image_file_id") and data.get("edit_image_ext"):
            await save_image(bot, data["edit_image_file_id"], slug, data["edit_image_ext"])
            image_url = image_db_url(slug, data["edit_image_ext"])
            logger.info("Replaced image for slug=%s → %s", slug, image_url)

        # 3. Update database (ID and slug never change)
        game = await update_game(
            slug        = slug,
            name        = data["edit_name"],
            description = data["edit_description"],
            image_url   = image_url,
            html_file   = data["edit_html_file"],
            category    = data["edit_category"],
            tags        = data.get("edit_tags", ""),
            active      = data.get("edit_active", True),
        )

        # 4. Remove confirm buttons from preview message
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        # 5. Confirmation summary
        active_str = "🌍 Ommaviy" if game.get("active") else "🔒 Yopiq"
        await callback.message.answer(
            "✅ <b>O'yin muvaffaqiyatli yangilandi!</b>\n\n"
            f"🆔 Slug: <code>{game['slug']}</code>\n"
            f"📛 Nomi: <b>{game['name']}</b>\n"
            f"📝 Ta'rif: {game['description']}\n"
            f"🗂 Kategoriya: {game['category']}\n"
            f"🏷 Teglar: {game.get('tags') or '—'}\n"
            f"📄 HTML: <code>{game['html_file']}</code>\n"
            f"👁 Ko'rinish: {active_str}\n\n"
            f"Ko'rish: /oyinlar {game['slug']}"
            f"{gh_status_line}",
            parse_mode="HTML",
        )

        # 6. Show the live game card (only if public)
        if game.get("active"):
            from services.game_service import send_game_card
            await send_game_card(callback.message, game)

        logger.info("Admin updated game: slug=%s", slug)

    except Exception:
        logger.exception("Failed to update game slug=%s", slug)
        await callback.message.answer(
            "❌ Xato yuz berdi. Qayta urinib ko'ring: /tuzatish"
        )


# ── Confirm: Yana tahrirlash (restart from step 1) ───────────────────────────

@router.callback_query(F.data == "edit:restart", EditGameFSM.waiting_confirm)
async def cb_restart(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("✏️ Qayta tahrirlash...")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # Keep all edit_* values so the next pass shows already-changed values
    await _ask_name(callback.message, state)


# ── Step → next-step dispatch map ─────────────────────────────────────────────
# Must be defined AFTER all _ask_* functions to avoid forward-reference issues.

_NEXT_STEP = {
    EditGameFSM.waiting_name.state:        _ask_description,
    EditGameFSM.waiting_description.state: _ask_image,
    EditGameFSM.waiting_image.state:       _ask_html,
    EditGameFSM.waiting_html.state:        _ask_category,
    EditGameFSM.waiting_category.state:    _ask_tags,
    EditGameFSM.waiting_tags.state:        _ask_visibility,
    EditGameFSM.waiting_visibility.state:  _ask_confirm,
}
