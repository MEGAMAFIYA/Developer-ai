"""AI Developer — AI API Sozlamalari (refactored).

Four independent controls, each with its own FSM state:
  ✏️  Providerni o'zgartirish  → AIProviderStates.waiting_provider
  🧠  Modelni o'zgartirish     → AIModelStates.waiting_model
  🔑  API Keyni o'zgartirish   → AIKeyStates.waiting_key
  🔌  Ulanishni tekshirish     → direct callback (no FSM)

Each control is fully independent — changing provider never asks for model
or key, and vice-versa.  After any change reload_manager() is called
immediately so the bot works with new credentials without a restart.

Priority at reload:
  1. DB values (set here via Telegram) — always win
  2. Env vars / config.py             — fallback if DB is empty
  3. Provider-level defaults          — handled inside provider classes
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from database.global_db import delete_setting, get_setting, set_setting
from handlers.developer.modules.ai.callbacks import (
    AI_KEY_CHANGE,
    AI_KEY_DELETE,
    AI_KEY_DELETE_OK,
    AI_KEY_SETTINGS,
    AI_KEY_TEST,
    AI_MENU,
    AI_MODEL_CHANGE,
    AI_PROVIDER_CHANGE,
)
from handlers.developer.modules.ai import services
from handlers.developer.modules.ai.states import (
    AIKeyStates,
    AIModelStates,
    AIProviderStates,
)

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:key_manager")

_VALID_PROVIDERS = ("openai", "openrouter", "gemini", "claude", "deepseek")


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


async def _guard_cb(query: CallbackQuery) -> bool:
    if _is_admin(query.from_user.id):
        return True
    await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


async def _guard_msg(message: Message) -> bool:
    if _is_admin(message.from_user.id):
        return True
    await message.answer("⛔ Ruxsat yo'q.")
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _settings_keyboard(has_key: bool) -> InlineKeyboardMarkup:
    """Main 🔑 AI API Sozlamalari screen keyboard."""
    rows = [
        [InlineKeyboardButton(text="✏️ Providerni o'zgartirish", callback_data=AI_PROVIDER_CHANGE)],
        [InlineKeyboardButton(text="🧠 Modelni o'zgartirish",    callback_data=AI_MODEL_CHANGE)],
        [InlineKeyboardButton(text="🔑 API Keyni o'zgartirish",  callback_data=AI_KEY_CHANGE)],
        [InlineKeyboardButton(text="🔌 Ulanishni tekshirish",    callback_data=AI_KEY_TEST)],
    ]
    if has_key:
        rows.append([
            InlineKeyboardButton(text="🗑 API Keyni o'chirish", callback_data=AI_KEY_DELETE),
        ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, o'chir", callback_data=AI_KEY_DELETE_OK),
        InlineKeyboardButton(text="❌ Bekor",       callback_data=AI_KEY_SETTINGS),
    ]])


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=AI_KEY_SETTINGS),
    ]])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="⬅️ AI API Sozlamalariga qaytish",
            callback_data=AI_KEY_SETTINGS,
        ),
    ]])


# ── Helper: build and display the main settings screen ───────────────────────

async def _show_settings(target, *, edit: bool = True) -> None:
    """Render the 🔑 AI API Sozlamalari screen.

    target: CallbackQuery (edit=True) or Message (edit=False).
    """
    text = services.build_status_text()
    s    = services.get_ai_status()
    kb   = _settings_keyboard(has_key=s["has_key"])
    if edit and hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        msg = target.message if hasattr(target, "message") else target
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


# ── Helper: reload manager using DB values with env-var fallback ──────────────

async def _reload(overrides: dict | None = None) -> None:
    """Reload the AI manager, applying DB → env priority.

    overrides: dict with any of {provider, api_key, model} to use instead of
    their DB values (used when we've just written to DB and want to avoid a
    second read).
    """
    ov = overrides or {}
    provider = ov.get("provider") or (await get_setting("ai_provider")) or cfg.config.AI_PROVIDER or ""
    api_key  = ov.get("api_key")  or (await get_setting("ai_api_key")) or cfg.config.AI_API_KEY  or ""
    model    = ov.get("model")    or (await get_setting("ai_model"))   or cfg.config.AI_MODEL    or ""
    services.reload_manager(provider=provider, api_key=api_key, model=model)


# ══════════════════════════════════════════════════════════════════════════════
# Entry: open settings screen
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_KEY_SETTINGS)
async def cb_key_settings(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await query.answer()
    await _show_settings(query, edit=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1. ✏️ Provider change
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_PROVIDER_CHANGE)
async def cb_provider_change_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    current = (await get_setting("ai_provider")) or cfg.config.AI_PROVIDER or "—"
    providers_fmt = " · ".join(f"<code>{p}</code>" for p in _VALID_PROVIDERS)
    await state.set_state(AIProviderStates.waiting_provider)
    await query.answer()
    await query.message.edit_text(
        f"✏️ <b>Providerni o'zgartirish</b>\n\n"
        f"Joriy provider: <code>{current}</code>\n\n"
        f"Yangi provider nomini yuboring:\n{providers_fmt}",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AIProviderStates.waiting_provider)
async def msg_provider_input(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    raw = (message.text or "").strip().lower()
    if raw not in _VALID_PROVIDERS:
        providers_fmt = " · ".join(f"<code>{p}</code>" for p in _VALID_PROVIDERS)
        await message.answer(
            f"⚠️ Noto'g'ri provider: <code>{raw}</code>\n\n"
            f"Qabul qilinadigan providerlar:\n{providers_fmt}",
            reply_markup=_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    await set_setting("ai_provider", raw)
    await _reload(overrides={"provider": raw})
    await state.clear()

    await message.answer(
        f"✅ <b>Provider o'zgartirildi</b>\n\n"
        f"Yangi provider: <code>{raw}</code>\n"
        f"<i>Bot restart qilmasdan yangi sozlama qo'llanildi.</i>",
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. 🧠 Model change
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_MODEL_CHANGE)
async def cb_model_change_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    s = services.get_ai_status()
    current_model = s["model"] or "—"
    await state.set_state(AIModelStates.waiting_model)
    await query.answer()
    await query.message.edit_text(
        f"🧠 <b>Modelni o'zgartirish</b>\n\n"
        f"Joriy model: <code>{current_model}</code>\n\n"
        f"Yangi model nomini yuboring.\n"
        f"<i>Masalan: <code>qwen/qwen3-coder:free</code>, "
        f"<code>gpt-4o</code>, <code>gemini-1.5-pro</code>, "
        f"<code>claude-3-5-sonnet-20241022</code></i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AIModelStates.waiting_model)
async def msg_model_input(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "⚠️ Model nomi bo'sh bo'lishi mumkin emas.",
            reply_markup=_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    await set_setting("ai_model", raw)
    await _reload(overrides={"model": raw})
    await state.clear()

    await message.answer(
        f"✅ <b>Model o'zgartirildi</b>\n\n"
        f"Yangi model: <code>{raw}</code>\n"
        f"<i>Bot restart qilmasdan yangi sozlama qo'llanildi.</i>",
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3. 🔑 API Key change
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_KEY_CHANGE)
async def cb_key_change_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.set_state(AIKeyStates.waiting_key)
    await query.answer()
    await query.message.edit_text(
        "🔑 <b>API Keyni o'zgartirish</b>\n\n"
        "Yangi API kalitingizni yuboring.\n"
        "<i>Xavfsizlik uchun xabar yuborilgach darhol o'chiriladi.</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AIKeyStates.waiting_key)
async def msg_key_input(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    raw = (message.text or "").strip()

    # Delete the message immediately — key must not remain visible in chat
    try:
        await message.delete()
    except Exception:
        pass

    if not raw:
        await message.answer(
            "⚠️ API key bo'sh bo'lishi mumkin emas.",
            reply_markup=_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    await set_setting("ai_api_key", raw)
    await _reload(overrides={"api_key": raw})
    await state.clear()

    masked = services.mask_key(raw)
    await message.answer(
        f"🔑 <b>API Key saqlandi</b>\n\n"
        f"Kalit: <code>{masked}</code>\n"
        f"<i>Xavfsiz bazada saqlandi. Bot restart qilmasdan ishlaydi.</i>",
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4. 🗑 Delete API key
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_KEY_DELETE)
async def cb_key_delete_confirm(query: CallbackQuery) -> None:
    if not await _guard_cb(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🗑 <b>API Keyni o'chirish</b>\n\n"
        "Haqiqatan ham API keyni o'chirmoqchimisiz?\n"
        "<i>Bu amal qaytarib bo'lmaydi — AI funksiyalari ishlamay qoladi.</i>",
        reply_markup=_confirm_delete_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_KEY_DELETE_OK)
async def cb_key_delete_execute(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await query.answer()
    await delete_setting("ai_api_key")
    # Reload with empty key; provider/model remain
    provider = (await get_setting("ai_provider")) or cfg.config.AI_PROVIDER or ""
    model    = (await get_setting("ai_model"))    or cfg.config.AI_MODEL    or ""
    services.reload_manager(provider=provider, api_key="", model=model)
    await state.clear()
    await query.message.edit_text(
        "✅ <b>API Key o'chirildi</b>\n\n"
        "AI funksiyalari endi ishlamaydi.\n"
        "Yangi key kiritish uchun <b>🔑 API Keyni o'zgartirish</b> tugmasini bosing.",
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 5. 🔌 Test connection
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_KEY_TEST)
async def cb_key_test(query: CallbackQuery) -> None:
    if not await _guard_cb(query):
        return
    await query.answer()
    sent = await query.message.edit_text(
        "🔌 <b>Ulanish tekshirilmoqda…</b>\n\n"
        "Providerga so'rov yuborilmoqda, iltimos kuting.",
        parse_mode="HTML",
    )
    # Uses the live manager (DB priority applied at startup / after each change)
    result = await services.test_connection()
    s = services.get_ai_status()
    if result.ok:
        text = f"✅ <b>Ulanish muvaffaqiyatli!</b>\n\n{result.content}"
    else:
        text = f"❌ <b>Ulanish xatosi</b>\n\n{result.error}"
    await sent.edit_text(
        text,
        reply_markup=_settings_keyboard(has_key=s["has_key"]),
        parse_mode="HTML",
    )
