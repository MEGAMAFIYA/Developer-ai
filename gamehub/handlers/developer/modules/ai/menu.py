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
    # Phase 3 — live features
    AI_CHAT, AI_WRITE_CODE, AI_EDIT_CODE, AI_ANALYZE_CODE,
    AI_CREATE_GAME, AI_IMPROVE_GAME, AI_FIND_BUG, AI_FIX_BUG,
    # Phase 4 — tool manager entry points
    AI_FILE_MANAGER, AI_DB_MANAGER, AI_GH_MANAGER, AI_PROJ_MANAGER, AI_LOG_VIEW,
    # Phase 4 — key management
    AI_KEY_SETTINGS,
)

# ── Menu display text ─────────────────────────────────────────────────────────

AI_MENU_TEXT = (
    "🤖 <b>AI Developer</b>\n\n"
    "Sun'iy intellekt yordamida o'yinlaringizni\n"
    "yarating, tahrirlang va rivojlantiring.\n\n"
    "<i>Kerakli bo'limni tanlang:</i>"
)


def ai_menu_text_with_status() -> str:
    """Menu text that includes a live API connection status line."""
    from handlers.developer.modules.ai.services import get_ai_status
    s = get_ai_status()
    if s["configured"]:
        status = f"✅ AI ulangan ({s['provider']})"
    elif s["provider"] and not s["has_key"]:
        status = f"❌ API key kiritilmagan ({s['provider']})"
    else:
        status = "❌ AI sozlanmagan"
    return (
        f"🤖 <b>AI Developer</b>\n\n"
        f"Holat: {status}\n\n"
        "Sun'iy intellekt yordamida o'yinlaringizni\n"
        "yarating, tahrirlang va rivojlantiring.\n\n"
        "<i>Kerakli bo'limni tanlang:</i>"
    )

# ── Keyboard builders ─────────────────────────────────────────────────────────

def ai_menu_keyboard() -> InlineKeyboardMarkup:
    """2-column grid for AI Developer sub-menu."""

    # ── Phase 3 — live AI features ────────────────────────────────────────────
    live_items = [
        (AI_CHAT,         "💬 AI Chat"),
        (AI_WRITE_CODE,   "📝 Kod yozdirish"),
        (AI_EDIT_CODE,    "✏️ Kodni tahrirlash"),
        (AI_ANALYZE_CODE, "🔍 Kodni tahlil qilish"),
        (AI_CREATE_GAME,  "🎮 O'yin yaratish"),
        (AI_IMPROVE_GAME, "🛠 O'yinni yaxshilash"),
        (AI_FIND_BUG,     "🧠 Bug topish"),
        (AI_FIX_BUG,      "❌ Xatoni tuzatish"),
    ]

    # ── Phase 1/2 stubs (coming soon) ─────────────────────────────────────────
    stub_items = [
        (AI_DESIGN,   "🎨 Dizayn"),
        (AI_IMAGE,    "🖼 Rasm"),
        (AI_GAMEPLAY, "🎮 Gameplay"),
        (AI_CODE,     "🧩 Kod yaratuvchi"),
        (AI_BUILDER,  "🪄 AI Builder"),
        (AI_ASSETS,   "📦 Assets"),
        (AI_PREVIEW,  "👁 Preview"),
        (AI_TEST,     "🧪 Test"),
    ]

    rows = []

    # Live features section
    for i in range(0, len(live_items), 2):
        pair = live_items[i: i + 2]
        rows.append([
            InlineKeyboardButton(text=label, callback_data=cb)
            for cb, label in pair
        ])

    # Divider row (visual separator via disabled-looking text isn't possible,
    # so we just leave a blank-ish label row — kept for future use)
    # Stub section (2 columns)
    for i in range(0, len(stub_items), 2):
        pair = stub_items[i: i + 2]
        rows.append([
            InlineKeyboardButton(text=label, callback_data=cb)
            for cb, label in pair
        ])

    # Phase 4 — Tool Managers (2-column grid)
    tool_items = [
        (AI_FILE_MANAGER, "📂 File Manager"),
        (AI_DB_MANAGER,   "🗄 Database"),
        (AI_GH_MANAGER,   "🐙 GitHub"),
        (AI_PROJ_MANAGER, "🔧 Project Tools"),
    ]
    for i in range(0, len(tool_items), 2):
        pair = tool_items[i: i + 2]
        rows.append([
            InlineKeyboardButton(text=label, callback_data=cb)
            for cb, label in pair
        ])

    # Phase 4 — Action log (full-width)
    rows.append([
        InlineKeyboardButton(text="📋 Action Log", callback_data=AI_LOG_VIEW),
    ])

    # Phase 4 — API key management (full-width)
    rows.append([
        InlineKeyboardButton(text="🔑 API Sozlamalar", callback_data=AI_KEY_SETTINGS),
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
