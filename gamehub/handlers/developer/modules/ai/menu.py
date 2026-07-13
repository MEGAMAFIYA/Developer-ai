"""AI Developer module — sub-menu text and keyboard builder.

Import `ai_menu_keyboard()` and `AI_MENU_TEXT` from here (not from
handlers.py) to avoid circular imports between menu and handlers.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from handlers.developer.callbacks import DEV_MENU          # ⬅️ back to dev main
from handlers.developer.modules.ai.callbacks import (
    AI_MENU,
    AI_DESIGN, AI_IMAGE, AI_GAMEPLAY, AI_CODE,
    AI_BUILDER, AI_ASSETS, AI_PREVIEW, AI_TEST,
)

# ── Menu display text ─────────────────────────────────────────────────────────

AI_MENU_TEXT = (
    "🤖 <b>AI Developer</b>\n\n"
    "Sun'iy intellekt yordamida o'yinlaringizni\n"
    "yarating, tahrirlang va rivojlantiring.\n\n"
    "<i>Kerakli bo'limni tanlang:</i>"
)

# ── Keyboard builders ─────────────────────────────────────────────────────────

def ai_menu_keyboard() -> InlineKeyboardMarkup:
    """2-column grid for AI Developer sub-menu."""
    items = [
        (AI_DESIGN,   "🎨 Dizaynni o'zgartirish"),
        (AI_IMAGE,    "🖼 Rasm almashtirish"),
        (AI_GAMEPLAY, "🎮 Gameplayni o'zgartirish"),
        (AI_CODE,     "🧠 Kod yozish"),
        (AI_BUILDER,  "🪄 AI Builder"),
        (AI_ASSETS,   "📦 Asset yuklash"),
        (AI_PREVIEW,  "👁 Preview"),
        (AI_TEST,     "🧪 Test"),
    ]

    rows = []
    for i in range(0, len(items), 2):
        pair = items[i: i + 2]
        rows.append([
            InlineKeyboardButton(text=label, callback_data=cb)
            for cb, label in pair
        ])

    # Footer: back to Developer Mode main menu
    rows.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_MENU),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def ai_back_keyboard() -> InlineKeyboardMarkup:
    """Single button: back to AI Developer sub-menu."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU),
    ]])
