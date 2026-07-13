"""AI Developer Phase 4 — Database Tools.

Features
────────
🗄 SQL so'rov         — execute SQL against global or game DB
                        SELECT: auto-execute
                        UPDATE / INSERT / DELETE / DROP / TRUNCATE / ALTER / CREATE:
                        show preview → confirm → execute

📊 Database statistikasi — read-only stats for both DBs (row counts, table sizes)

Safety rules
────────────
• DML and DDL always require explicit confirmation.
• SELECT queries run immediately.
• Every executed query is logged via action_log.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from database.global_db import get_global_pool
from database.game_db   import get_game_pool
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL, AI_MENU,
    AI_DB_QUERY, AI_DB_STATS, AI_DB_OK,
    AI_DB_GLOBAL, AI_DB_GAME,
)
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:database_tools")

_TG_MAX = 4096

# Patterns that require confirmation
_DANGEROUS = re.compile(
    r"^\s*(UPDATE|INSERT|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


# ── FSM States ────────────────────────────────────────────────────────────────

class DBStates(StatesGroup):
    choosing_db = State()   # which DB? global | game
    waiting_sql = State()   # receive SQL text
    confirming  = State()   # DML: show query + confirm before execute


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID

async def _guard_cb(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("Ruxsat yo'q.", show_alert=True)
    return False

async def _guard_msg(m: Message) -> bool:
    if _is_admin(m.from_user.id):
        return True
    await m.answer("Ruxsat yo'q.")
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _db_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Global DB", callback_data=AI_DB_GLOBAL),
            InlineKeyboardButton(text="Game DB",   callback_data=AI_DB_GAME),
        ],
        [InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL)],
    ])

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])

def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash", callback_data=AI_DB_OK),
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_pool(db: str):
    """Return the asyncpg pool for 'global' or 'game'."""
    if db == "game":
        return await get_game_pool()
    return await get_global_pool()

def _is_dangerous(sql: str) -> bool:
    return bool(_DANGEROUS.match(sql.strip()))

def _fmt_rows(rows: list[Any], max_rows: int = 50) -> str:
    """Format asyncpg Record list as a simple table string."""
    if not rows:
        return "(bo'sh natija)"
    header = " | ".join(str(k) for k in rows[0].keys())
    sep    = "-" * min(len(header), 80)
    body   = "\n".join(
        " | ".join(str(v) for v in row.values())
        for row in rows[:max_rows]
    )
    result = f"{header}\n{sep}\n{body}"
    if len(rows) > max_rows:
        result += f"\n... +{len(rows) - max_rows} qator"
    return result

async def _run_sql(db: str, sql: str) -> tuple[bool, str]:
    """Execute SQL; return (success, message)."""
    try:
        pool = await _get_pool(db)
        async with pool.acquire() as conn:
            if _is_dangerous(sql):
                status = await conn.execute(sql)
                return True, str(status)
            else:
                rows = await conn.fetch(sql)
                return True, _fmt_rows(rows)
    except Exception as exc:
        return False, str(exc)


# ════════════════════════════════════════════════════════════════════════════
# 🗄 SQL so'rov
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_DB_QUERY)
async def cb_db_query_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(DBStates.choosing_db)
    await q.answer()
    await q.message.edit_text(
        "<b>SQL so'rov</b>\n\n"
        "Qaysi ma'lumotlar bazasiga so'rov yuborasiz?\n\n"
        "<b>Global DB</b> — o'yinlar katalogi\n"
        "<b>Game DB</b>   — natijalar va olmoslar",
        reply_markup=_db_choice_kb(), parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data in (AI_DB_GLOBAL, AI_DB_GAME),
    StateFilter(DBStates.choosing_db),
)
async def cb_db_chosen(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    db = "global" if q.data == AI_DB_GLOBAL else "game"
    await state.update_data(db=db)
    await state.set_state(DBStates.waiting_sql)
    await q.answer()
    await q.message.edit_text(
        f"<b>SQL so'rov</b> — {db.upper()} DB\n\n"
        "SQL so'rovini yozing:\n\n"
        "<code>SELECT * FROM games LIMIT 10</code>\n"
        "<code>SELECT COUNT(*) FROM scores</code>\n\n"
        "SELECT: darhol bajariladi.\n"
        "UPDATE/INSERT/DELETE: avval tasdiqlash so'raladi.",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


@router.message(DBStates.waiting_sql)
async def msg_db_sql(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    sql  = (m.text or "").strip()
    data = await state.get_data()
    db   = data.get("db", "global")

    if not sql:
        await m.answer("So'rov bo'sh.", reply_markup=_cancel_kb())
        return

    if _is_dangerous(sql):
        # Needs confirmation
        await state.update_data(sql=sql)
        await state.set_state(DBStates.confirming)
        await m.answer(
            f"<b>DML so'rov — tasdiqlash</b>\n\n"
            f"DB: <b>{db.upper()}</b>\n\n"
            f"<pre>{sql[:800]}</pre>\n\n"
            "Bu so'rov ma'lumotlarni <b>o'zgartiradi</b>.\n"
            "Tasdiqlaysizmi?",
            reply_markup=_confirm_kb(), parse_mode="HTML",
        )
    else:
        # SELECT — auto-execute
        await state.clear()
        sent = await m.answer(f"Bajarilmoqda ({db.upper()} DB)...")
        ok, result = await _run_sql(db, sql)
        icon = "Natija" if ok else "Xato"
        text = f"<b>{icon}</b> ({db.upper()} DB)\n\n<pre>{result[:3000]}</pre>"
        await sent.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(m.from_user.id, "DB_SELECT", f"{db}:{sql[:100]}",
                         "ok" if ok else f"error:{result[:80]}")


@router.callback_query(
    lambda c: c.data == AI_DB_OK,
    StateFilter(DBStates.confirming),
)
async def cb_db_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    db   = data.get("db", "global")
    sql  = data.get("sql", "")
    await state.clear()
    await q.answer()
    sent = await q.message.edit_text(
        f"Bajarilmoqda ({db.upper()} DB)...", parse_mode="HTML"
    )
    ok, result = await _run_sql(db, sql)
    icon = "Bajarildi" if ok else "Xato"
    text = f"<b>{icon}</b> ({db.upper()} DB)\n\n<pre>{result[:2500]}</pre>"
    await sent.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await log_action(q.from_user.id, "DB_DML", f"{db}:{sql[:100]}",
                     "ok" if ok else f"error:{result[:80]}")


# ════════════════════════════════════════════════════════════════════════════
# 📊 Database statistikasi
# ════════════════════════════════════════════════════════════════════════════

_STATS_QUERIES = {
    "global": [
        ("Jami o'yinlar",     "SELECT COUNT(*) AS count FROM games"),
        ("Faol o'yinlar",     "SELECT COUNT(*) AS count FROM games WHERE active=true"),
        ("Kategoriyalar",     "SELECT category, COUNT(*) AS n FROM games GROUP BY category ORDER BY n DESC"),
    ],
    "game": [
        ("Jami natijalar",    "SELECT COUNT(*) AS count FROM scores"),
        ("Unikal foydalanuvchilar", "SELECT COUNT(DISTINCT user_id) AS count FROM scores"),
        ("Top o'yinlar",      "SELECT game_name, COUNT(*) AS n FROM scores GROUP BY game_name ORDER BY n DESC LIMIT 5"),
        ("Olmoslar",          "SELECT COUNT(*) AS count, COALESCE(SUM(balance),0) AS total FROM diamonds"),
    ],
}


@router.callback_query(lambda c: c.data == AI_DB_STATS)
async def cb_db_stats(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    await q.message.edit_text("Ma'lumotlar yig'ilmoqda...", parse_mode="HTML")

    lines = ["<b>Database statistikasi</b>\n"]
    for db_name, queries in _STATS_QUERIES.items():
        lines.append(f"\n<b>{db_name.upper()} DB</b>")
        try:
            pool = await _get_pool(db_name)
            async with pool.acquire() as conn:
                for label, sql in queries:
                    rows = await conn.fetch(sql)
                    val  = _fmt_rows(rows, max_rows=10)
                    lines.append(f"• {label}:\n<pre>{val}</pre>")
        except Exception as exc:
            lines.append(f"Xato: <code>{exc}</code>")

    text = "\n".join(lines)
    # Split if too long
    for i in range(0, len(text), _TG_MAX):
        chunk = text[i: i + _TG_MAX]
        kb    = _back_kb() if i + _TG_MAX >= len(text) else None
        await q.message.answer(chunk, reply_markup=kb, parse_mode="HTML")

    await log_action(q.from_user.id, "DB_STATS", "both", "ok")
