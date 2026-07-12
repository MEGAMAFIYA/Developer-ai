"""Handler: /reyting — per-game leaderboards (global and per-group).

Flow
----
/reyting
  → inline buttons: one per active game   (callback: rg:{slug})
  → user picks a game
  → inline buttons: 🌍 Global | 👥 Guruh  (callback: rgl:{slug} | rgr:{slug})
  → formatted leaderboard sent as a message
"""

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.global_db import get_all_games, get_game_by_slug
from database.game_db import (
    get_global_leaderboard,
    get_group_leaderboard,
    get_global_player_count,
    get_group_player_count,
)

logger = logging.getLogger(__name__)
router = Router()

# Medals for top 3
_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _display_name(row: dict) -> str:
    uname = (row.get("username") or "").strip()
    fname = (row.get("first_name") or "").strip()
    if uname:
        return f"@{uname}"
    return fname or f"ID:{row['user_id']}"


def _format_score(n: int) -> str:
    """Comma-separate thousands: 12345 → 12,345."""
    return f"{n:,}"


def _build_leaderboard_text(
    game: dict,
    entries: list[dict],
    total_players: int,
    scope_label: str,
) -> str:
    header = f"🎮 <b>{game['name']} — {scope_label}</b>\n"

    if not entries:
        return header + "\n😔 Hali hech qanday natija yo'q.\n\nO'ynang va birinchi bo'ling! 🏆"

    lines: list[str] = [header, ""]
    for i, row in enumerate(entries, start=1):
        medal = _MEDALS.get(i, f"{i:>2}.")
        name  = _display_name(row)
        score = _format_score(int(row["best_score"]))
        lines.append(f"{medal} {name} — {score}")

    lines.append("")
    lines.append(f"👤 Jami o'yinchilar: <b>{total_players}</b>")
    return "\n".join(lines)


def _game_list_keyboard(games: list[dict]) -> InlineKeyboardMarkup:
    """One button per game, 2-column grid.  callback: rg:{slug}"""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for g in games:
        row.append(InlineKeyboardButton(
            text=g["name"],
            callback_data=f"rg:{g['slug']}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _scope_keyboard(slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌍 Global",  callback_data=f"rgl:{slug}"),
        InlineKeyboardButton(text="👥 Guruh",   callback_data=f"rgr:{slug}"),
    ]])


# ---------------------------------------------------------------------------
# /reyting command
# ---------------------------------------------------------------------------

@router.message(Command("reyting"))
async def cmd_reyting(message: Message) -> None:
    games = await get_all_games(only_active=True)

    if not games:
        await message.answer("😔 Hozircha hech qanday o'yin mavjud emas.")
        return

    await message.answer(
        "📊 <b>Reyting</b>\n\nQaysi o'yin reytingini ko'rmoqchisiz?",
        parse_mode="HTML",
        reply_markup=_game_list_keyboard(games),
    )


# ---------------------------------------------------------------------------
# Step 1: game selected → show scope choice
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("rg:"))
async def cb_select_game(callback: CallbackQuery) -> None:
    slug = callback.data[3:]
    game = await get_game_by_slug(slug)

    if not game:
        await callback.answer("❌ O'yin topilmadi!", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        f"📊 <b>{game['name']}</b>\n\nQaysi reytingni ko'rmoqchisiz?",
        parse_mode="HTML",
        reply_markup=_scope_keyboard(slug),
    )


# ---------------------------------------------------------------------------
# Step 2a: 🌍 Global leaderboard
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("rgl:"))
async def cb_global(callback: CallbackQuery) -> None:
    slug = callback.data[4:]
    game = await get_game_by_slug(slug)
    if not game:
        await callback.answer("❌ O'yin topilmadi!", show_alert=True)
        return

    await callback.answer("⏳ Yuklanmoqda...")

    entries = await get_global_leaderboard(slug, limit=20)
    total   = await get_global_player_count(slug)
    text    = _build_leaderboard_text(game, entries, total, "🌍 Global Reyting")

    # Add back-button to change scope
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Orqaga", callback_data=f"rg:{slug}"),
    ]])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb)


# ---------------------------------------------------------------------------
# Step 2b: 👥 Group leaderboard
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("rgr:"))
async def cb_group(callback: CallbackQuery) -> None:
    slug    = callback.data[4:]
    chat    = callback.message.chat
    chat_id = chat.id

    # Only works in group / supergroup / channel
    if chat.type == "private":
        await callback.answer(
            "⚠️ Guruh reytingini ko'rish uchun ushbu buyruqni guruhda yuboring.",
            show_alert=True,
        )
        return

    game = await get_game_by_slug(slug)
    if not game:
        await callback.answer("❌ O'yin topilmadi!", show_alert=True)
        return

    await callback.answer("⏳ Yuklanmoqda...")

    chat_name   = chat.title or f"Guruh {chat_id}"
    entries     = await get_group_leaderboard(slug, chat_id, limit=20)
    total       = await get_group_player_count(slug, chat_id)
    scope_label = f"👥 {chat_name}"
    text        = _build_leaderboard_text(game, entries, total, scope_label)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Orqaga", callback_data=f"rg:{slug}"),
    ]])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb)
