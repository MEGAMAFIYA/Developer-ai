"""Developer Mode › 🎮 O'yinlar

Features
────────
📋 Barcha o'yinlar — slugi, nomi, holati, kategoriyasi
✅/❌ Faollashtirish/o'chirish — bir marta bosish bilan toggle
🔄 Qayta yuklash    — initial games ni qayta seed qilish (tasdiq kerak)
📊 Natijalar soni  — har bir o'yin bo'yicha play count
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config as cfg
from database.global_db import get_global_pool, get_all_games
from database.game_db import get_game_pool
from database.setup import INITIAL_GAMES, add_game
from handlers.developer.callbacks import (
    DEV_GAMES,
    DEV_GAMES_LIST,
    DEV_GAMES_RESEED,
    DEV_GAMES_RESEED_OK,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:games")

_TG_MAX    = 4096
_TOG_PFX   = "dev:games:tog:"   # dynamic: dev:games:tog:<slug>


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

async def _games_keyboard(games: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for g in games:
        icon = "✅" if g["active"] else "❌"
        slug = g["slug"]
        rows.append([InlineKeyboardButton(
            text=f"{icon} {g['name']}",
            callback_data=f"{_TOG_PFX}{slug}",
        )])
    rows.append([
        InlineKeyboardButton(text="🔄 Qayta yuklash", callback_data=DEV_GAMES_RESEED),
        InlineKeyboardButton(text="⬅️ Orqaga",        callback_data="dev:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_reseed_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, qayta yuklash", callback_data=DEV_GAMES_RESEED_OK),
        InlineKeyboardButton(text="❌ Bekor",             callback_data=DEV_GAMES),
    ]])


# ── Data helpers ──────────────────────────────────────────────────────────────

async def _game_text(games: list[dict]) -> str:
    if not games:
        return "🎮 <b>O'yinlar</b>\n\nHech qanday o'yin topilmadi."

    # get play counts
    try:
        spool = await get_game_pool()
        rows  = await spool.fetch(
            "SELECT game_name, COUNT(*) AS cnt FROM scores GROUP BY game_name"
        )
        counts = {r["game_name"]: r["cnt"] for r in rows}
    except Exception:
        counts = {}

    lines = [f"🎮 <b>O'yinlar ({len(games)} ta)</b>\n"]
    for g in games:
        icon = "✅" if g["active"] else "❌"
        plays = counts.get(g["name"], 0)
        lines.append(
            f"{icon} <b>{g['name']}</b> <code>[{g['slug']}]</code>\n"
            f"   Kategoriya: {g['category']} | O'yinlar: {plays}"
        )
    lines.append("\n📌 O'yinni bosib faollashtirish/o'chirishingiz mumkin.")
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data in (DEV_GAMES, DEV_GAMES_LIST))
async def cb_games_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    games = await get_all_games(only_active=False)
    text  = await _game_text(games)
    kb    = await _games_keyboard(games)
    await q.message.edit_text(text[:_TG_MAX], reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data.startswith(_TOG_PFX))
async def cb_game_toggle(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    slug = q.data[len(_TOG_PFX):]
    try:
        pool = await get_global_pool()
        row  = await pool.fetchrow(
            "SELECT * FROM games WHERE slug = $1", slug
        )
        if not row:
            await q.answer("O'yin topilmadi.", show_alert=True)
            return
        new_state = not row["active"]
        await pool.execute(
            "UPDATE games SET active = $1 WHERE slug = $2", new_state, slug
        )
        action_word = "faollashtirildi" if new_state else "o'chirildi"
        await q.answer(f"{'✅' if new_state else '❌'} {row['name']} {action_word}")
        await log_action(
            q.from_user.id, "GAME_TOGGLE", slug,
            f"active={new_state}"
        )
    except Exception as exc:
        logger.error("game toggle %s: %s", slug, exc)
        await q.answer(f"Xato: {exc}", show_alert=True)
        return

    # refresh list
    games = await get_all_games(only_active=False)
    text  = await _game_text(games)
    kb    = await _games_keyboard(games)
    try:
        await q.message.edit_text(text[:_TG_MAX], reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(lambda c: c.data == DEV_GAMES_RESEED)
async def cb_games_reseed(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🔄 <b>Qayta yuklash</b>\n\n"
        "Bu amal barcha boshlang'ich o'yinlarni qayta qo'shadi "
        "(mavjudlar yangilanadi, yo'qolgan ma'lumotlar tiklanadi).\n\n"
        "⚠️ <b>Davom etasizmi?</b>",
        reply_markup=_confirm_reseed_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_GAMES_RESEED_OK)
async def cb_games_reseed_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Yuklanmoqda…")
    try:
        for game in INITIAL_GAMES:
            await add_game(**game)
        await log_action(
            q.from_user.id, "GAMES_RESEED",
            f"{len(INITIAL_GAMES)} ta o'yin", "ok"
        )
        games = await get_all_games(only_active=False)
        text  = await _game_text(games)
        kb    = await _games_keyboard(games)
        await q.message.edit_text(
            f"✅ {len(INITIAL_GAMES)} ta o'yin qayta yuklandi.\n\n" + text[:3800],
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("reseed error: %s", exc)
        await q.message.edit_text(
            f"❌ Xato: {exc}",
            reply_markup=back_keyboard(),
            parse_mode="HTML",
        )
