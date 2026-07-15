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
