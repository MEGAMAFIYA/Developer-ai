"""Developer Mode › 📊 Statistika

Features
────────
📊 Umumiy ko'rsatkichlar — foydalanuvchilar, o'yinlar, natijalar
👥 Foydalanuvchilar      — jami, faol (7/30 kun), yangi (bugun)
🎮 O'yinlar             — faol/nofaol soni, kategoriyalar
🏆 Natijalar             — jami, bugun, eng yaxshi o'yin
🔄 Yangilash             — barcha ma'lumotlarni qayta yuklash
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config as cfg
from database.global_db import get_global_pool
from database.game_db import get_game_pool
from handlers.developer.callbacks import (
    DEV_STATS,
    DEV_STATS_REFRESH,
    DEV_STATS_USERS,
    DEV_STATS_GAMES,
    DEV_STATS_SCORES,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:stats")

_TG_MAX = 4096


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data=DEV_STATS_USERS),
            InlineKeyboardButton(text="🎮 O'yinlar",        callback_data=DEV_STATS_GAMES),
        ],
        [
            InlineKeyboardButton(text="🏆 Natijalar",       callback_data=DEV_STATS_SCORES),
            InlineKeyboardButton(text="🔄 Yangilash",       callback_data=DEV_STATS_REFRESH),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="dev:menu")],
    ])


# ── Data helpers ──────────────────────────────────────────────────────────────

async def _overview() -> str:
    """Quick summary: users, games, scores."""
    try:
        gpool = await get_global_pool()
        game_total = await gpool.fetchval("SELECT COUNT(*) FROM games") or 0
        game_active = await gpool.fetchval("SELECT COUNT(*) FROM games WHERE active = TRUE") or 0

        spool = await get_game_pool()
        score_total = await spool.fetchval("SELECT COUNT(*) FROM scores") or 0
        user_total  = await spool.fetchval("SELECT COUNT(DISTINCT user_id) FROM scores") or 0

        lines = [
            "📊 <b>Statistika — Umumiy ko'rinish</b>\n",
            f"👥 Foydalanuvchilar (jami): <b>{user_total}</b>",
            f"🎮 O'yinlar: <b>{game_active}</b> faol / <b>{game_total}</b> jami",
            f"🏆 Natijalar (jami): <b>{score_total}</b>",
            "",
            "📌 Batafsil ma'lumot uchun tugmalardan foydalaning.",
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.error("stats overview error: %s", exc)
        return f"❌ Ma'lumot olishda xato: {exc}"


async def _user_stats() -> str:
    try:
        spool = await get_game_pool()
        total   = await spool.fetchval("SELECT COUNT(DISTINCT user_id) FROM scores") or 0
        last7   = await spool.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM scores "
            "WHERE created_at >= NOW() - INTERVAL '7 days'"
        ) or 0
        last30  = await spool.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM scores "
            "WHERE created_at >= NOW() - INTERVAL '30 days'"
        ) or 0
        today   = await spool.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM scores "
            "WHERE created_at::date = CURRENT_DATE"
        ) or 0

        lines = [
            "👥 <b>Foydalanuvchilar statistikasi</b>\n",
            f"Jami o'ynagan:    <b>{total}</b>",
            f"So'nggi 7 kunda:  <b>{last7}</b>",
            f"So'nggi 30 kunda: <b>{last30}</b>",
            f"Bugun:            <b>{today}</b>",
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.error("user stats error: %s", exc)
        return f"❌ Xato: {exc}"


async def _game_stats() -> str:
    try:
        gpool = await get_global_pool()
        rows = await gpool.fetch(
            "SELECT name, active, category FROM games ORDER BY created_at"
        )
        active   = [r for r in rows if r["active"]]
        inactive = [r for r in rows if not r["active"]]

        cats: dict[str, int] = {}
        for r in rows:
            cats[r["category"]] = cats.get(r["category"], 0) + 1

        lines = [
            "🎮 <b>O'yinlar statistikasi</b>\n",
            f"Faol:    <b>{len(active)}</b>",
            f"Nofaol: <b>{len(inactive)}</b>",
            f"Jami:    <b>{len(rows)}</b>",
            "",
            "📂 <b>Kategoriyalar:</b>",
        ]
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {cnt}")

        if rows:
            lines += ["", "📋 <b>Barcha o'yinlar:</b>"]
            for r in rows:
                mark = "✅" if r["active"] else "❌"
                lines.append(f"  {mark} {r['name']} <i>({r['category']})</i>")

        return "\n".join(lines)
    except Exception as exc:
        logger.error("game stats error: %s", exc)
        return f"❌ Xato: {exc}"


async def _score_stats() -> str:
    try:
        spool = await get_game_pool()
        total  = await spool.fetchval("SELECT COUNT(*) FROM scores") or 0
        today  = await spool.fetchval(
            "SELECT COUNT(*) FROM scores WHERE created_at::date = CURRENT_DATE"
        ) or 0
        week   = await spool.fetchval(
            "SELECT COUNT(*) FROM scores WHERE created_at >= NOW() - INTERVAL '7 days'"
        ) or 0
        best_rows = await spool.fetch(
            """
            SELECT game_name, COUNT(*) AS plays, MAX(score) AS top
            FROM scores
            GROUP BY game_name
            ORDER BY plays DESC
            LIMIT 5
            """
        )

        lines = [
            "🏆 <b>Natijalar statistikasi</b>\n",
            f"Jami natijalar:     <b>{total}</b>",
            f"Bugun:              <b>{today}</b>",
            f"So'nggi 7 kun:      <b>{week}</b>",
            "",
            "🎮 <b>Eng ko'p o'ynalgan (top 5):</b>",
        ]
        for r in best_rows:
            lines.append(
                f"  {r['game_name']}: {r['plays']} o'yin, "
                f"eng yuqori: {r['top']}"
            )

        return "\n".join(lines)
    except Exception as exc:
        logger.error("score stats error: %s", exc)
        return f"❌ Xato: {exc}"


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_STATS)
async def cb_stats_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _overview()
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_stats_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_STATS_REFRESH)
async def cb_stats_refresh(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("🔄 Yangilanmoqda…")
    text = await _overview()
    try:
        await q.message.edit_text(
            text[:_TG_MAX], reply_markup=_stats_keyboard(), parse_mode="HTML"
        )
    except Exception:
        pass  # no change


@router.callback_query(lambda c: c.data == DEV_STATS_USERS)
async def cb_stats_users(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _user_stats()
    await q.message.edit_text(
        text[:_TG_MAX],
        reply_markup=_stats_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_STATS_GAMES)
async def cb_stats_games(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _game_stats()
    await q.message.edit_text(
        text[:_TG_MAX],
        reply_markup=_stats_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_STATS_SCORES)
async def cb_stats_scores(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _score_stats()
    await q.message.edit_text(
        text[:_TG_MAX],
        reply_markup=_stats_keyboard(),
        parse_mode="HTML",
    )
