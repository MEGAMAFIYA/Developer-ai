"""Developer Mode › 🗄 Database Manager

Features
────────
📋 Jadvallar   — har bir jadval bo'yicha qator soni va o'lcham
🔍 SQL So'rov  — faqat o'qish uchun (SELECT) SQL so'rovlar (FSM)
📥 CSV Eksport — games yoki scores jadvalini CSV sifatida yuborish
🧹 Vacuum      — VACUUM ANALYZE (tasdiq kerak)
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from database.global_db import get_global_pool
from database.game_db import get_game_pool
from handlers.developer.callbacks import (
    DEV_DATABASE,
    DEV_DB_TABLES,
    DEV_DB_QUERY,
    DEV_DB_EXPORT_G,
    DEV_DB_EXPORT_S,
    DEV_DB_VACUUM,
    DEV_DB_VACUUM_OK,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:database")

_TG_MAX = 4096


# ── FSM ───────────────────────────────────────────────────────────────────────

class DBFSM(StatesGroup):
    waiting_sql = State()


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _db_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Jadvallar",     callback_data=DEV_DB_TABLES),
            InlineKeyboardButton(text="🔍 SQL So'rov",    callback_data=DEV_DB_QUERY),
        ],
        [
            InlineKeyboardButton(text="📥 Games CSV",     callback_data=DEV_DB_EXPORT_G),
            InlineKeyboardButton(text="📥 Scores CSV",    callback_data=DEV_DB_EXPORT_S),
        ],
        [
            InlineKeyboardButton(text="🧹 Vacuum",        callback_data=DEV_DB_VACUUM),
            InlineKeyboardButton(text="⬅️ Orqaga",        callback_data="dev:menu"),
        ],
    ])


def _confirm_vacuum_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, Vacuum",  callback_data=DEV_DB_VACUUM_OK),
        InlineKeyboardButton(text="❌ Bekor",        callback_data=DEV_DATABASE),
    ]])


# ── Data helpers ──────────────────────────────────────────────────────────────

async def _table_info() -> str:
    lines = ["🗄 <b>Jadvallar holati</b>\n"]
    try:
        gpool = await get_global_pool()
        for tbl in ("games", "settings"):
            cnt  = await gpool.fetchval(f"SELECT COUNT(*) FROM {tbl}") or 0
            size = await gpool.fetchval(
                "SELECT pg_size_pretty(pg_total_relation_size($1))", tbl
            ) or "?"
            lines.append(f"📋 <b>{tbl}</b>: {cnt} qator ({size})")
    except Exception as exc:
        lines.append(f"⚠️ Global DB xato: {exc}")

    try:
        spool = await get_game_pool()
        for tbl in ("scores", "diamonds"):
            cnt  = await spool.fetchval(f"SELECT COUNT(*) FROM {tbl}") or 0
            size = await spool.fetchval(
                "SELECT pg_size_pretty(pg_total_relation_size($1))", tbl
            ) or "?"
            lines.append(f"📋 <b>{tbl}</b>: {cnt} qator ({size})")
    except Exception as exc:
        lines.append(f"⚠️ Game DB xato: {exc}")

    return "\n".join(lines)


def _is_safe_sql(sql: str) -> bool:
    """Only allow SELECT statements (no mutation)."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return False
    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                 "TRUNCATE", "CREATE", "GRANT", "REVOKE")
    for kw in forbidden:
        if kw in stripped:
            return False
    return True


async def _run_sql(sql: str) -> str:
    """Execute a safe SELECT and return formatted results."""
    try:
        # Try global pool first; if table not found, try game pool
        try:
            pool = await get_global_pool()
            rows = await pool.fetch(sql)
        except Exception:
            pool = await get_game_pool()
            rows = await pool.fetch(sql)

        if not rows:
            return "✅ So'rov bajarildi — natija yo'q."

        cols  = list(rows[0].keys())
        lines = [" | ".join(cols), "-" * min(60, len(" | ".join(cols)))]
        for r in rows[:50]:
            lines.append(" | ".join(str(r[c]) for c in cols))
        if len(rows) > 50:
            lines.append(f"… yana {len(rows) - 50} qator (faqat 50 ta ko'rsatildi)")
        return "<pre>" + "\n".join(lines) + "</pre>"
    except Exception as exc:
        return f"❌ SQL xato: {exc}"


async def _export_games_csv() -> BufferedInputFile:
    pool = await get_global_pool()
    rows = await pool.fetch("SELECT * FROM games ORDER BY id")
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    return BufferedInputFile(buf.getvalue().encode("utf-8"), filename="games.csv")


async def _export_scores_csv() -> BufferedInputFile:
    pool = await get_game_pool()
    rows = await pool.fetch("SELECT * FROM scores ORDER BY id LIMIT 10000")
    buf  = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    return BufferedInputFile(buf.getvalue().encode("utf-8"), filename="scores.csv")


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_DATABASE)
async def cb_database_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🗄 <b>Database Manager</b>\n\nQuyidagi amallardan birini tanlang:",
        reply_markup=_db_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_DB_TABLES)
async def cb_db_tables(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _table_info()
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_db_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_DB_QUERY)
async def cb_db_query_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.set_state(DBFSM.waiting_sql)
    await q.message.edit_text(
        "🔍 <b>SQL So'rov</b>\n\n"
        "Faqat <code>SELECT</code> so'rovlari ruxsat etiladi.\n"
        "Misol: <code>SELECT * FROM games LIMIT 5</code>\n\n"
        "So'rovni kiriting:",
        reply_markup=back_keyboard("❌ Bekor"),
        parse_mode="HTML",
    )


@router.message(StateFilter(DBFSM.waiting_sql))
async def msg_db_query(m: Message, state: FSMContext) -> None:
    if not _is_admin(m.from_user.id):
        return
    await state.clear()
    sql = (m.text or "").strip()
    if not sql:
        await m.answer("❌ So'rov bo'sh.", reply_markup=back_keyboard())
        return
    if not _is_safe_sql(sql):
        await m.answer(
            "⛔ Faqat <b>SELECT</b> so'rovlari ruxsat etiladi.",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return
    msg = await m.answer("⏳ So'rov bajarilmoqda…")
    result = await _run_sql(sql)
    await log_action(m.from_user.id, "DB_QUERY", sql[:100], "ok")
    await msg.edit_text(
        result[:_TG_MAX], reply_markup=back_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_DB_EXPORT_G)
async def cb_db_export_games(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ CSV tayyorlanmoqda…")
    try:
        doc = await _export_games_csv()
        await q.message.answer_document(doc, caption="📥 games.csv")
        await log_action(q.from_user.id, "DB_EXPORT", "games", "ok")
    except Exception as exc:
        await q.message.answer(f"❌ Export xatosi: {exc}")


@router.callback_query(lambda c: c.data == DEV_DB_EXPORT_S)
async def cb_db_export_scores(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ CSV tayyorlanmoqda…")
    try:
        doc = await _export_scores_csv()
        await q.message.answer_document(doc, caption="📥 scores.csv")
        await log_action(q.from_user.id, "DB_EXPORT", "scores", "ok")
    except Exception as exc:
        await q.message.answer(f"❌ Export xatosi: {exc}")


@router.callback_query(lambda c: c.data == DEV_DB_VACUUM)
async def cb_db_vacuum(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🧹 <b>Vacuum ANALYZE</b>\n\n"
        "Bu amal barcha jadvallarni tozalaydi va statistikani yangilaydi.\n"
        "Amal bir necha soniya davom etishi mumkin.\n\n"
        "⚠️ Davom etasizmi?",
        reply_markup=_confirm_vacuum_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_DB_VACUUM_OK)
async def cb_db_vacuum_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Vacuum bajarilmoqda…")
    errors = []
    try:
        gpool = await get_global_pool()
        async with gpool.acquire() as conn:
            await conn.execute("VACUUM ANALYZE games")
            await conn.execute("VACUUM ANALYZE settings")
    except Exception as exc:
        errors.append(f"Global DB: {exc}")
    try:
        spool = await get_game_pool()
        async with spool.acquire() as conn:
            await conn.execute("VACUUM ANALYZE scores")
    except Exception as exc:
        errors.append(f"Game DB: {exc}")

    await log_action(
        q.from_user.id, "DB_VACUUM",
        "games,settings,scores",
        "ok" if not errors else f"errors={errors}",
    )
    result = "✅ Vacuum muvaffaqiyatli bajarildi!" if not errors else \
             "⚠️ Vacuum bajarildi, lekin xatolar bor:\n" + "\n".join(errors)
    await q.message.edit_text(
        result, reply_markup=_db_keyboard(), parse_mode="HTML"
    )
