"""AI Developer module — all callback handlers.

Architecture notes
──────────────────
• Every handler is a thin dispatcher: validate admin → answer → show UI.
• Business logic lives in services/ (future: services/ai_service.py).
• FSM states are imported from states.py; set them here when ready.
• To wire OpenAI/Claude: add a service call between the answer() and
  edit_text() calls below — the rest of the flow stays the same.

Adding a new sub-feature
────────────────────────
1. Add callback constant to callbacks.py
2. Add FSM states to states.py (if stateful)
3. Add a button row to menu.py → ai_menu_keyboard()
4. Add a handler function below following the same pattern
5. Register it in __init__.py → router.include_router(...)
   (or just add it here; this file is already included)
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

import config as cfg
from handlers.developer.callbacks import DEV_AI          # entry point from dev menu
from handlers.developer.modules.ai.callbacks import (
    AI_MENU,
    AI_DESIGN, AI_IMAGE, AI_GAMEPLAY, AI_CODE,
    AI_BUILDER, AI_ASSETS, AI_PREVIEW, AI_TEST,
    AI_LOG_VIEW,
)
from handlers.developer.modules.ai.menu import ai_menu_keyboard, ai_back_keyboard, AI_MENU_TEXT
from handlers.developer.modules.ai.action_log import read_recent

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:handlers")

_COMING_SOON = "🚧 Ushbu funksiya hali ishlab chiqilmoqda."


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


async def _guard(query: CallbackQuery) -> bool:
    """Return True if allowed; answer with alert and return False if not."""
    if _is_admin(query.from_user.id):
        return True
    await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Entry point: DEV_AI → show AI sub-menu ────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_AI)
async def cb_ai_menu_entry(query: CallbackQuery) -> None:
    """Called when admin taps 🤖 AI Developer from the main dev menu."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        AI_MENU_TEXT,
        reply_markup=ai_menu_keyboard(),
        parse_mode="HTML",
    )


# ── AI_MENU: back to AI sub-menu (from any feature screen) ───────────────────

@router.callback_query(lambda c: c.data == AI_MENU)
async def cb_ai_menu_back(query: CallbackQuery) -> None:
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        AI_MENU_TEXT,
        reply_markup=ai_menu_keyboard(),
        parse_mode="HTML",
    )


# ── 🎨 Dizaynni o'zgartirish ─────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_DESIGN)
async def cb_ai_design(query: CallbackQuery) -> None:
    """Future: send AI a prompt → patch game CSS/layout."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🎨 <b>Dizaynni o'zgartirish</b>\n\n"
        "O'yinning vizual dizayni (ranglar, shriftlar, layout)\n"
        "sun'iy intellekt yordamida o'zgartiriladi.\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 🖼 Rasm almashtirish ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_IMAGE)
async def cb_ai_image(query: CallbackQuery) -> None:
    """Future: replace game thumbnail / in-game sprites."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🖼 <b>Rasm almashtirish</b>\n\n"
        "O'yin rasmi yoki sprite faylini yangi rasm bilan\n"
        "almashtirishingiz mumkin bo'ladi.\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 🎮 Gameplayni o'zgartirish ───────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_GAMEPLAY)
async def cb_ai_gameplay(query: CallbackQuery) -> None:
    """Future: describe gameplay change in Uzbek/Russian → AI patches JS logic."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🎮 <b>Gameplayni o'zgartirish</b>\n\n"
        "O'yin mexanikasi, tezlik, qiyinchilik darajasi va\n"
        "boshqa parametrlarni AI yordamida o'zgartiring.\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 🧠 Kod yozish ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_CODE)
async def cb_ai_code(query: CallbackQuery) -> None:
    """Future: natural-language → HTML5/JS/CSS code generation via OpenAI."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🧠 <b>Kod yozish</b>\n\n"
        "Tabiiy tilda vazifani yozing — AI siz uchun\n"
        "HTML5, JavaScript yoki CSS kod yozib beradi.\n\n"
        "Qo'llab-quvvatlanadi: <i>OpenAI GPT-4o · Claude 3.5 · Gemini</i>\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 🪄 AI Builder ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_BUILDER)
async def cb_ai_builder(query: CallbackQuery) -> None:
    """Future: describe a game → AI generates complete HTML5 game from scratch."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🪄 <b>AI Builder</b>\n\n"
        "O'yin g'oyasini tasvirlab bering — AI to'liq\n"
        "HTML5 canvas o'yinini yaratib beradi.\n\n"
        "Janrlar: <i>Arcade · Puzzle · Runner · Shooter</i>\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 📦 Asset yuklash ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_ASSETS)
async def cb_ai_assets(query: CallbackQuery) -> None:
    """Future: upload image, audio, sprite files linked to a specific game."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "📦 <b>Asset yuklash</b>\n\n"
        "O'yinlarga rasm, audio va sprite fayllarni\n"
        "yuklash va bog'lash mumkin bo'ladi.\n\n"
        "Qo'llab-quvvatlanadigon formatlar:\n"
        "<i>Rasm: PNG · JPG · WebP · SVG\n"
        "Audio: MP3 · OGG · WAV\n"
        "Sprite: PNG spritesheets</i>\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 👁 Preview ────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_PREVIEW)
async def cb_ai_preview(query: CallbackQuery) -> None:
    """Future: send a live WebApp link for any game directly in chat."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "👁 <b>Preview</b>\n\n"
        "Istalgan o'yinni to'g'ridan-to'g'ri chatda\n"
        "WebApp sifatida ochib ko'rish mumkin bo'ladi.\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 🧪 Test ───────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_TEST)
async def cb_ai_test(query: CallbackQuery) -> None:
    """Future: run automated tests on AI-generated code before applying it."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🧪 <b>Test</b>\n\n"
        "AI tomonidan yaratilgan kodlarni o'yinga\n"
        "qo'shishdan oldin avtomatik sinab ko'rish.\n\n"
        + _COMING_SOON,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )


# ── 📋 Action Log ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_LOG_VIEW)
async def cb_log_view(query: CallbackQuery) -> None:
    """Show the last 30 entries from ai_actions.log."""
    if not await _guard(query):
        return
    await query.answer()
    await query.message.edit_text("📋 Log o'qilmoqda...", parse_mode="HTML")
    recent = await read_recent(30)
    text = (
        "📋 <b>Action Log</b> (so'nggi 30 ta)\n\n"
        f"<pre>{recent[:3600]}</pre>"
    )
    await query.message.edit_text(
        text,
        reply_markup=ai_back_keyboard(),
        parse_mode="HTML",
    )
