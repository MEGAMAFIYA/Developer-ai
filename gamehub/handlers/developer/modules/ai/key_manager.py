"""AI Developer — Phase 4: API Key Management.

Provides the admin with a dedicated screen to:
  • See current API connection status (✅ / ❌)
  • Enter or change the API key via Telegram FSM
  • Delete the stored API key
  • Test the connection with a real request to the provider

Architecture
────────────
• API key is stored in the `settings` DB table (key="ai_api_key").
• Provider and model are also persisted (key="ai_provider", "ai_model").
• On startup (main.py → init_databases → load_ai_settings_from_db) the
  singleton in services.py is reloaded from DB values.
• After any change here, reload_manager() is called immediately so the
  bot uses the new credentials without a restart.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import StateFilter
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
)
from handlers.developer.modules.ai.menu import ai_menu_text_with_status, ai_menu_keyboard
from handlers.developer.modules.ai import services
from handlers.developer.modules.ai.states import AIKeyStates

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

def _key_settings_keyboard(has_key: bool) -> InlineKeyboardMarkup:
    rows = []
    rows.append([
        InlineKeyboardButton(text="✏️ API Kalitni o'zgartirish", callback_data=AI_KEY_CHANGE),
    ])
    rows.append([
        InlineKeyboardButton(text="🔌 Ulanishni tekshirish", callback_data=AI_KEY_TEST),
    ])
    if has_key:
        rows.append([
            InlineKeyboardButton(text="🗑 API Kalitni o'chirish", callback_data=AI_KEY_DELETE),
        ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o'chir", callback_data=AI_KEY_DELETE_OK),
            InlineKeyboardButton(text="❌ Bekor", callback_data=AI_KEY_SETTINGS),
        ],
    ])


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=AI_KEY_SETTINGS),
    ]])


def _back_to_ai_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


# ── Helper: build and show the key settings screen ───────────────────────────

async def _show_key_screen(target, edit: bool = True) -> None:
    """Show the API key management screen.

    target: a CallbackQuery (edit=True) or Message (edit=False).
    """
    s = services.get_ai_status()
    text = services.build_status_text()
    kb   = _key_settings_keyboard(has_key=s["has_key"])
    if edit and hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        msg = target.message if hasattr(target, "message") else target
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


# ── Entry: open key settings screen ──────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_KEY_SETTINGS)
async def cb_key_settings(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await query.answer()
    await _show_key_screen(query, edit=True)


# ── Change / Enter API key ────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_KEY_CHANGE)
async def cb_key_change_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return

    provider = (await get_setting("ai_provider")) or cfg.config.AI_PROVIDER or ""

    await state.set_state(AIKeyStates.waiting_key)
    await state.update_data(provider=provider)
    await query.answer()

    provider_hint = f"<code>{provider}</code>" if provider else "sozlanmagan"
    await query.message.edit_text(
        f"🔑 <b>API Kalitni kiritish</b>\n\n"
        f"Joriy provider: {provider_hint}\n\n"
        f"Yangi API kalitingizni yuboring.\n"
        f"<i>Xavfsizlik uchun xabar yuborilgach o'chiriladi.</i>\n\n"
        f"Provider o'rnatilmagan bo'lsa, avval provider nomini "
        f"yozing (masalan: <code>openai</code>).\n"
        f"Mavjud providerlar: <code>openai · openrouter · gemini · claude · deepseek</code>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AIKeyStates.waiting_key)
async def msg_key_input(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return

    raw = (message.text or "").strip()

    # Delete the message immediately so the key is not visible in chat
    try:
        await message.delete()
    except Exception:
        pass

# Provider nomi yuborilgan bo'lsa, uni o'zgartir
    if raw.lower() in _VALID_PROVIDERS:
    provider = raw.lower()

    await set_setting("ai_provider", provider)
    await state.update_data(provider=provider)

    await message.answer(
        f"✅ Provider o'zgartirildi: <code>{provider}</code>\n\n"
        "Endi API kalitni yuboring.",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )
    return

    data = await state.get_data()
    provider = data.get("provider", "")

    # If provider is still unset, treat first word as provider, rest as key
    if not provider:
        parts = raw.split(maxsplit=1)
        if len(parts) == 2 and parts[0].lower() in _VALID_PROVIDERS:
            provider = parts[0].lower()
            raw = parts[1].strip()
        else:
            await message.answer(
                "⚠️ Provider o'rnatilmagan.\n"
                f"Iltimos, avval provider nomini yozing:\n"
                f"<code>openai · openrouter · gemini · claude · deepseek</code>",
                reply_markup=_cancel_keyboard(),
                parse_mode="HTML",
            )
            return

    # Persist to DB
    await set_setting("ai_provider", provider)
    await set_setting("ai_api_key", raw)

    # Reload manager singleton with new credentials
    model = (await get_setting("ai_model")) or cfg.config.AI_MODEL or ""
    services.reload_manager(provider=provider, api_key=raw, model=model)

    await state.clear()

    status = services.get_ai_status()
    status_line = "✅ Ulangan" if status["configured"] else "⚠️ Kalit saqlandi (tekshirish tavsiya etiladi)"

    sent = await message.answer(
        f"🔑 <b>API Kalit saqlandi</b>\n\n"
        f"Holat: {status_line}\n"
        f"Provider: <code>{provider}</code>\n\n"
        f"<i>Kalit xavfsiz bazada saqlandi.</i>",
        reply_markup=_back_to_ai_menu_keyboard(),
        parse_mode="HTML",
    )
    _ = sent  # kept for reference


# ── Delete API key ────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_KEY_DELETE)
async def cb_key_delete_confirm(query: CallbackQuery) -> None:
    if not await _guard_cb(query):
        return
    await query.answer()
    await query.message.edit_text(
        "🗑 <b>API Kalitni o'chirish</b>\n\n"
        "Haqiqatan ham API kalitni o'chirmoqchimisiz?\n"
        "Bu amal qaytarib bo'lmaydi — AI funksiyalari "
        "ishlamay qoladi.",
        reply_markup=_confirm_delete_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_KEY_DELETE_OK)
async def cb_key_delete_execute(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await query.answer()

    await delete_setting("ai_api_key")

    # Keep provider/model in DB but reload manager with empty key
    provider = (await get_setting("ai_provider")) or cfg.config.AI_PROVIDER or ""
    model    = (await get_setting("ai_model"))    or cfg.config.AI_MODEL    or ""
    services.reload_manager(provider=provider, api_key="", model=model)

    await state.clear()
    await query.message.edit_text(
        "✅ <b>API Kalit o'chirildi</b>\n\n"
        "AI funksiyalari endi ishlamaydi.\n"
        "Yangi kalit kiritish uchun <b>API Sozlamalar</b>ga qayting.",
        reply_markup=_back_to_ai_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Test connection ───────────────────────────────────────────────────────────

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

    result = await services.test_connection()

    if result.ok:
        text = (
            f"✅ <b>Ulanish muvaffaqiyatli!</b>\n\n"
            f"{result.content}"
        )
    else:
        text = (
            f"❌ <b>Ulanish xatosi</b>\n\n"
            f"{result.error}"
        )

    await sent.edit_text(
        text,
        reply_markup=_key_settings_keyboard(has_key=services.get_ai_status()["has_key"]),
        parse_mode="HTML",
    )
