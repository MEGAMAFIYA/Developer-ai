"""Developer Mode › 🔄 Backup Manager

Features
────────
📥 Games JSON   — games jadvalini JSON sifatida yuborish
📥 Scores CSV   — scores jadvalini CSV sifatida yuborish (max 10 000)
📦 Hammasi ZIP  — ikkala faylni bir ZIPda yuborish (tasdiq kerak)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from datetime import datetime

from aiogram import Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config as cfg
from database.global_db import get_global_pool
from database.game_db import get_game_pool
from handlers.developer.callbacks import (
    DEV_BACKUP,
    DEV_BAK_GAMES,
    DEV_BAK_SCORES,
    DEV_BAK_ALL,
    DEV_BAK_ALL_OK,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:backup")

_TG_MAX = 4096
_TS     = lambda: datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: E731


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _backup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Games JSON",  callback_data=DEV_BAK_GAMES),
            InlineKeyboardButton(text="📥 Scores CSV",  callback_data=DEV_BAK_SCORES),
        ],
        [
            InlineKeyboardButton(text="📦 Hammasi ZIP", callback_data=DEV_BAK_ALL),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="dev:menu")],
    ])


def _confirm_all_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, ZIP yaratish", callback_data=DEV_BAK_ALL_OK),
        InlineKeyboardButton(text="❌ Bekor",             callback_data=DEV_BACKUP),
    ]])


# ── Data helpers ──────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


async def _games_json_bytes() -> bytes:
    pool = await get_global_pool()
    rows = await pool.fetch("SELECT * FROM games ORDER BY id")
    data = []
    for r in rows:
        d = dict(r)
        # convert non-serialisable types
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        data.append(d)
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


async def _scores_csv_bytes() -> bytes:
    pool = await get_game_pool()
    rows = await pool.fetch("SELECT * FROM scores ORDER BY id DESC LIMIT 10000")
    buf  = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    return buf.getvalue().encode("utf-8")


async def _make_zip() -> tuple[bytes, str]:
    ts     = _TS()
    g_data = await _games_json_bytes()
    s_data = await _scores_csv_bytes()
    buf    = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"games_{ts}.json",  g_data)
        zf.writestr(f"scores_{ts}.csv",  s_data)
    return buf.getvalue(), f"backup_{ts}.zip"


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_BACKUP)
async def cb_backup_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🔄 <b>Backup Manager</b>\n\n"
        "Ma'lumotlar bazasini zaxiralash uchun quyidagi amalni tanlang:\n\n"
        "• <b>Games JSON</b> — barcha o'yinlar (games jadval)\n"
        "• <b>Scores CSV</b> — oxirgi 10 000 ta natija (scores jadval)\n"
        "• <b>Hammasi ZIP</b> — ikkala fayl bitta arxivda",
        reply_markup=_backup_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_BAK_GAMES)
async def cb_bak_games(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ JSON tayyorlanmoqda…")
    try:
        data     = await _games_json_bytes()
        ts       = _TS()
        filename = f"games_{ts}.json"
        doc      = BufferedInputFile(data, filename=filename)
        await q.message.answer_document(
            doc,
            caption=f"📥 {filename}\nO'lcham: {_fmt_size(len(data))}",
        )
        await log_action(q.from_user.id, "BACKUP_GAMES", filename,
                         f"size={_fmt_size(len(data))}")
    except Exception as exc:
        logger.error("backup games error: %s", exc)
        await q.message.answer(f"❌ Xato: {exc}")


@router.callback_query(lambda c: c.data == DEV_BAK_SCORES)
async def cb_bak_scores(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ CSV tayyorlanmoqda…")
    try:
        data     = await _scores_csv_bytes()
        ts       = _TS()
        filename = f"scores_{ts}.csv"
        doc      = BufferedInputFile(data, filename=filename)
        await q.message.answer_document(
            doc,
            caption=f"📥 {filename}\nO'lcham: {_fmt_size(len(data))}",
        )
        await log_action(q.from_user.id, "BACKUP_SCORES", filename,
                         f"size={_fmt_size(len(data))}")
    except Exception as exc:
        logger.error("backup scores error: %s", exc)
        await q.message.answer(f"❌ Xato: {exc}")


@router.callback_query(lambda c: c.data == DEV_BAK_ALL)
async def cb_bak_all_confirm(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "📦 <b>Hammasi ZIP</b>\n\n"
        "Quyidagi fayllar bir arxivga joylashtiriladi:\n"
        "• games_<ts>.json\n"
        "• scores_<ts>.csv\n\n"
        "Davom etasizmi?",
        reply_markup=_confirm_all_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_BAK_ALL_OK)
async def cb_bak_all_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ ZIP yaratilmoqda…")
    try:
        data, filename = await _make_zip()
        doc = BufferedInputFile(data, filename=filename)
        await q.message.answer_document(
            doc,
            caption=f"📦 {filename}\nO'lcham: {_fmt_size(len(data))}",
        )
        await log_action(q.from_user.id, "BACKUP_ALL", filename,
                         f"size={_fmt_size(len(data))}")
        await q.message.edit_text(
            f"✅ Backup tayyor: <code>{filename}</code>\n"
            f"O'lcham: {_fmt_size(len(data))}",
            reply_markup=_backup_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("backup all error: %s", exc)
        await q.message.edit_text(
            f"❌ ZIP yaratishda xato: {exc}",
            reply_markup=_backup_keyboard(),
            parse_mode="HTML",
        )
