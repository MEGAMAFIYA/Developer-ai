"""Developer Mode — reusable keyboard builders.

Import from here (not from menu.py) to avoid circular imports.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.developer.callbacks import (
    DEV_MENU, DEV_CLOSE,
    DEV_GAMES, DEV_AI, DEV_COMMANDS, DEV_FILES,
    DEV_DATABASE, DEV_STATS, DEV_GITHUB, DEV_SETTINGS,
    DEV_TEST, DEV_LOGS, DEV_BACKUP, DEV_PROJECT_MANAGER,
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the Developer Mode main menu (2-column grid + footer row)."""
    grid = [
        (DEV_GAMES,           "🎮 O'yinlar"),
        (DEV_AI,              "🤖 AI Developer"),
        (DEV_COMMANDS,        "🤖 Buyruqlar"),
        (DEV_FILES,           "📂 Fayllar"),
        (DEV_DATABASE,        "🗄 Database"),
        (DEV_STATS,           "📊 Statistika"),
        (DEV_GITHUB,          "🌐 GitHub"),
        (DEV_SETTINGS,        "⚙️ Sozlamalar"),
        (DEV_TEST,            "🧪 Test"),
        (DEV_LOGS,            "📜 Loglar"),
        (DEV_BACKUP,          "🔄 Backup"),
        (DEV_PROJECT_MANAGER, "📦 Project Manager"),
    ]

    # Pair up into 2-column rows; last item gets its own row if odd count
    rows = []
    for i in range(0, len(grid), 2):
        pair = grid[i: i + 2]
        rows.append([InlineKeyboardButton(text=label, callback_data=cb)
                     for cb, label in pair])

    # Footer: close button
    rows.append([InlineKeyboardButton(text="❌ Chiqish", callback_data=DEV_CLOSE)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard(label: str = "⬅️ Orqaga") -> InlineKeyboardMarkup:
    """Single back-to-menu button shown at the bottom of every sub-module."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data=DEV_MENU),
    ]])
