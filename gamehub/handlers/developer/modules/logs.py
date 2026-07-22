"""Developer Mode › 📜 Log Manager

Features
────────
📜 View latest logs        — last 50 lines of app.log with refresh button
🔄 Live tail / Refresh     — same view re-fetched on demand
🔍 Filter by level         — DEBUG / INFO / WARNING / ERROR / CRITICAL
🔎 Search logs             — FSM text search across app.log
📥 Download current log    — send app.log as document (auto-compress if >2 MB)
📦 Download all logs       — ZIP all .log files and send as document
🗑 Clear logs              — confirm → truncate app.log + ai_actions.log
📅 Filter by date          — FSM date input → show lines from that date
📋 AI Action Log           — view ai_actions.log (last 30 lines)

All destructive actions require confirmation.
Every action is logged to ai_actions.log via action_log.
"""

from __future__ import annotations

import asyncio
import html as _html
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from handlers.developer.callbacks import (
    DEV_LOGS,
    DEV_LOG_VIEW, DEV_LOG_REFRESH,
    DEV_LOG_FILTER,
    DEV_LOG_LVL_DBG, DEV_LOG_LVL_INF, DEV_LOG_LVL_WRN,
    DEV_LOG_LVL_ERR, DEV_LOG_LVL_CRT,
    DEV_LOG_SEARCH,
    DEV_LOG_DL_CUR, DEV_LOG_DL_ALL,
    DEV_LOG_CLEAR, DEV_LOG_CLEAR_OK,
    DEV_LOG_DATE,
    DEV_LOG_AI,
)
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:logs")

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE        = Path(__file__).resolve().parents[3]   # gamehub/
_LOG_DIR     = _BASE / "logs"
_APP_LOG     = _LOG_DIR / "app.log"
_AI_LOG      = _LOG_DIR / "ai_actions.log"
_TG_MAX      = 4096
_COMPRESS_AT = 2 * 1024 * 1024   # 2 MB — auto-compress above this

_LEVEL_LABELS = {
    DEV_LOG_LVL_DBG: "DEBUG",
    DEV_LOG_LVL_INF: "INFO",
    DEV_LOG_LVL_WRN: "WARNING",
    DEV_LOG_LVL_ERR: "ERROR",
    DEV_LOG_LVL_CRT: "CRITICAL",
}


# ── FSM States ────────────────────────────────────────────────────────────────

class LogFSM(StatesGroup):
    waiting_search = State()
    waiting_date   = State()
    confirm_clear  = State()


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID

async def _guard_cb(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False

async def _guard_msg(m: Message) -> bool:
    if _is_admin(m.from_user.id):
        return True
    await m.answer("⛔ Ruxsat yo'q.")
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📜 So'nggi loglar",  callback_data=DEV_LOG_VIEW),
            InlineKeyboardButton(text="📋 AI Action Log",   callback_data=DEV_LOG_AI),
        ],
        [
            InlineKeyboardButton(text="🔍 Level filtri",    callback_data=DEV_LOG_FILTER),
            InlineKeyboardButton(text="📅 Sana bo'yicha",   callback_data=DEV_LOG_DATE),
        ],
        [
            InlineKeyboardButton(text="🔎 Qidirish",        callback_data=DEV_LOG_SEARCH),
        ],
        [
            InlineKeyboardButton(text="📥 Joriy log",       callback_data=DEV_LOG_DL_CUR),
            InlineKeyboardButton(text="📦 Barcha loglar",   callback_data=DEV_LOG_DL_ALL),
        ],
        [
            InlineKeyboardButton(text="🗑 Loglarni tozalash", callback_data=DEV_LOG_CLEAR),
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga",          callback_data="dev:menu"),
        ],
    ])

def _level_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🐛 DEBUG",    callback_data=DEV_LOG_LVL_DBG),
            InlineKeyboardButton(text="ℹ️ INFO",     callback_data=DEV_LOG_LVL_INF),
        ],
        [
            InlineKeyboardButton(text="⚠️ WARNING",  callback_data=DEV_LOG_LVL_WRN),
            InlineKeyboardButton(text="❌ ERROR",    callback_data=DEV_LOG_LVL_ERR),
        ],
        [
            InlineKeyboardButton(text="🔴 CRITICAL", callback_data=DEV_LOG_LVL_CRT),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_LOGS)],
    ])

def _view_kb(show_refresh: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if show_refresh:
        rows.append([InlineKeyboardButton(text="🔄 Yangilash", callback_data=DEV_LOG_REFRESH)])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_LOGS)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=DEV_LOGS),
    ]])

def _back_log_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_LOGS),
    ]])


# ── File helpers ───────────────────────────────────────────────────────────────

def _tail(path: Path, n: int = 50) -> list[str]:
    """Return the last n lines of a file, or [] if missing."""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


def _read_all_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except Exception:
        return []


def _filter_by_level(lines: list[str], level: str) -> list[str]:
    return [l for l in lines if f"[{level}]" in l or f" {level} " in l]


def _filter_by_date(lines: list[str], date_str: str) -> list[str]:
    return [l for l in lines if l.startswith(date_str)]


def _search_lines(lines: list[str], query: str) -> list[str]:
    q = query.lower()
    return [l for l in lines if q in l.lower()]


def _fmt_log_block(lines: list[str], header: str, max_chars: int = 3200) -> str:
    """Build an HTML message block from log lines.

    The raw log content is HTML-escaped before being placed inside a <pre>
    block so that <, >, and & in error messages never break parse_mode="HTML".
    """
    body = "".join(lines)
    if not body:
        body = "(bo'sh)"
    if len(body) > max_chars:
        body = "...(qisqartirildi)...\n" + body[-max_chars:]
    return f"{header}\n<pre>{_html.escape(body)}</pre>"


def _log_summary() -> str:
    parts = []
    for path in [_APP_LOG, _AI_LOG]:
        if path.exists():
            size  = path.stat().st_size
            lines = sum(1 for _ in open(path, encoding="utf-8", errors="replace"))
            parts.append(f"• <code>{path.name}</code>: {lines:,} qator ({_fmt_size(size)})")
        else:
            parts.append(f"• <code>{path.name}</code>: mavjud emas")
    rotated = sorted(_LOG_DIR.glob("app.log.*")) if _LOG_DIR.exists() else []
    if rotated:
        total = sum(p.stat().st_size for p in rotated)
        parts.append(f"• Arxiv fayllar ({len(rotated)} ta): {_fmt_size(total)}")
    return "\n".join(parts)


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _all_log_files() -> list[Path]:
    if not _LOG_DIR.exists():
        return []
    return sorted(_LOG_DIR.glob("*.log")) + sorted(_LOG_DIR.glob("*.log.*"))


async def _compress_log(path: Path) -> Path:
    """Zip a single log file; return path to the zip."""
    zip_path = path.with_suffix(path.suffix + ".zip")
    def _do():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(path, path.name)
        return zip_path
    return await asyncio.to_thread(_do)


async def _zip_all_logs() -> Path:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = _LOG_DIR / f"logs_export_{ts}.zip"
    def _do():
        files = _all_log_files()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if f.suffix == ".zip":
                    continue
                zf.write(f, f.name)
        return zip_path
    return await asyncio.to_thread(_do)


# ════════════════════════════════════════════════════════════════════════════
# Entry point — main Log Manager menu
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOGS)
async def cb_logs_main(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()

    summary = await asyncio.to_thread(_log_summary)
    await q.message.edit_text(
        "📜 <b>Log Manager</b>\n\n"
        f"{summary}\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=_main_kb(),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════════════════════════
# 📜 View latest / Live tail
# ════════════════════════════════════════════════════════════════════════════

async def _do_view(q: CallbackQuery) -> None:
    lines = await asyncio.to_thread(_tail, _APP_LOG, 50)
    if not lines:
        text = (
            "📜 <b>So'nggi loglar</b>\n\n"
            f"<code>{_APP_LOG.name}</code> hali mavjud emas.\n"
            "Bot qayta ishga tushgandan so'ng fayl yaratiladi."
        )
    else:
        text = _fmt_log_block(lines, f"📜 <b>So'nggi 50 qator</b> — <code>{_APP_LOG.name}</code>")
    await q.message.edit_text(text, reply_markup=_view_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_LOG_VIEW)
async def cb_log_view(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await _do_view(q)
    await log_action(q.from_user.id, "LOG_VIEW", _APP_LOG.name, "ok")


@router.callback_query(lambda c: c.data == DEV_LOG_REFRESH)
async def cb_log_refresh(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer("🔄 Yangilanmoqda...")
    await _do_view(q)
    await log_action(q.from_user.id, "LOG_REFRESH", _APP_LOG.name, "ok")


# ════════════════════════════════════════════════════════════════════════════
# 📋 AI Action Log
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_AI)
async def cb_log_ai(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()

    lines = await asyncio.to_thread(_tail, _AI_LOG, 30)
    if not lines:
        text = (
            "📋 <b>AI Action Log</b>\n\n"
            "Hozircha hech qanday amal qayd etilmagan.\n"
            "AI Developer vositalari ishlatilganda bu yerda ko'rinadi."
        )
    else:
        text = _fmt_log_block(lines, f"📋 <b>AI Action Log</b> — so'nggi 30 ta yozuv")

    await q.message.edit_text(text, reply_markup=_back_log_kb(), parse_mode="HTML")
    await log_action(q.from_user.id, "LOG_AI_VIEW", _AI_LOG.name, f"lines={len(lines)}")


# ════════════════════════════════════════════════════════════════════════════
# 🔍 Filter by level
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_FILTER)
async def cb_log_filter_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "🔍 <b>Level bo'yicha filtrlash</b>\n\n"
        "Ko'rmoqchi bo'lgan log darajasini tanlang:",
        reply_markup=_level_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data in _LEVEL_LABELS)
async def cb_log_filter_level(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()
    level = _LEVEL_LABELS[q.data]

    all_lines = await asyncio.to_thread(_read_all_lines, _APP_LOG)
    filtered  = await asyncio.to_thread(_filter_by_level, all_lines, level)

    if not filtered:
        text = (
            f"🔍 <b>Level: {level}</b>\n\n"
            f"<code>{_APP_LOG.name}</code> da [{level}] yozuvlari topilmadi."
        )
    else:
        shown = filtered[-40:]
        text  = _fmt_log_block(
            shown,
            f"🔍 <b>Level: {level}</b> — {len(filtered):,} ta / so'nggi 40 ta ko'rsatilmoqda",
        )

    await q.message.edit_text(text, reply_markup=_back_log_kb(), parse_mode="HTML")
    await log_action(q.from_user.id, "LOG_FILTER", level, f"matches={len(filtered)}")


# ════════════════════════════════════════════════════════════════════════════
# 🔎 Search logs
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_SEARCH)
async def cb_log_search_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(LogFSM.waiting_search)
    await q.answer()
    await q.message.edit_text(
        "🔎 <b>Log qidirish</b>\n\n"
        "Qidiruv so'zini yozing:\n\n"
        "<code>ERROR</code>, <code>asyncpg</code>, <code>handler</code> ...",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(LogFSM.waiting_search)
async def msg_log_search(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    query = (m.text or "").strip()
    if not query:
        await m.answer("So'rov bo'sh.", reply_markup=_cancel_kb())
        return

    sent = await m.answer(f"🔎 <code>{query}</code> qidirilmoqda...", parse_mode="HTML")

    all_lines = await asyncio.to_thread(_read_all_lines, _APP_LOG)
    matches   = await asyncio.to_thread(_search_lines, all_lines, query)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_LOGS),
    ]])

    if not matches:
        await sent.edit_text(
            f"🔎 «<code>{query}</code>» topilmadi.",
            reply_markup=back_kb, parse_mode="HTML",
        )
    else:
        shown = matches[-30:]
        text  = _fmt_log_block(
            shown,
            f"🔎 «{query}» — {len(matches):,} natija / so'nggi 30 ta",
        )
        for i in range(0, len(text), _TG_MAX):
            chunk = text[i: i + _TG_MAX]
            kb    = back_kb if i + _TG_MAX >= len(text) else None
            if i == 0:
                await sent.edit_text(chunk, reply_markup=kb, parse_mode="HTML")
            else:
                await m.answer(chunk, reply_markup=kb, parse_mode="HTML")

    await log_action(m.from_user.id, "LOG_SEARCH", query, f"matches={len(matches)}")


# ════════════════════════════════════════════════════════════════════════════
# 📅 Filter by date
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_DATE)
async def cb_log_date_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(LogFSM.waiting_date)
    await q.answer()
    today = datetime.now().strftime("%Y-%m-%d")
    await q.message.edit_text(
        "📅 <b>Sana bo'yicha filtrlash</b>\n\n"
        f"Sanani yozing (YYYY-MM-DD formatida):\n\n"
        f"Masalan: <code>{today}</code>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(LogFSM.waiting_date)
async def msg_log_date(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    date_str = (m.text or "").strip()

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await m.answer(
            f"❌ Noto'g'ri format: <code>{date_str}</code>\n"
            "Misol: <code>2026-07-14</code>",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
        return

    sent = await m.answer(f"📅 <code>{date_str}</code> filtrlanyapti...", parse_mode="HTML")

    all_lines = await asyncio.to_thread(_read_all_lines, _APP_LOG)
    filtered  = await asyncio.to_thread(_filter_by_date, all_lines, date_str)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=DEV_LOGS),
    ]])

    if not filtered:
        await sent.edit_text(
            f"📅 <code>{date_str}</code> uchun log yozuvlari topilmadi.",
            reply_markup=back_kb, parse_mode="HTML",
        )
    else:
        shown = filtered[-40:]
        text  = _fmt_log_block(
            shown,
            f"📅 <b>{date_str}</b> — {len(filtered):,} ta / so'nggi 40 ta",
        )
        for i in range(0, len(text), _TG_MAX):
            chunk = text[i: i + _TG_MAX]
            kb    = back_kb if i + _TG_MAX >= len(text) else None
            if i == 0:
                await sent.edit_text(chunk, reply_markup=kb, parse_mode="HTML")
            else:
                await m.answer(chunk, reply_markup=kb, parse_mode="HTML")

    await log_action(m.from_user.id, "LOG_DATE", date_str, f"lines={len(filtered)}")


# ════════════════════════════════════════════════════════════════════════════
# 📥 Download current log
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_DL_CUR)
async def cb_log_dl_cur(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()

    if not _APP_LOG.exists():
        await q.message.edit_text(
            "📥 <b>app.log mavjud emas</b>\n\n"
            "Bot qayta ishga tushgandan so'ng fayl yaratiladi.",
            reply_markup=_back_log_kb(), parse_mode="HTML",
        )
        return

    size = _APP_LOG.stat().st_size
    await q.message.edit_text(
        f"⏳ Tayyorlanmoqda... ({_fmt_size(size)})", parse_mode="HTML"
    )

    try:
        if size > _COMPRESS_AT:
            zip_path = await _compress_log(_APP_LOG)
            doc      = FSInputFile(str(zip_path), filename=zip_path.name)
            caption  = (
                f"📦 <b>app.log.zip</b>\n"
                f"Original: {_fmt_size(size)} → Arxiv: {_fmt_size(zip_path.stat().st_size)}\n"
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            doc     = FSInputFile(str(_APP_LOG), filename=_APP_LOG.name)
            caption = (
                f"📥 <b>{_APP_LOG.name}</b>\n"
                f"Hajm: {_fmt_size(size)}\n"
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        await q.message.answer_document(doc, caption=caption, parse_mode="HTML")
        await q.message.edit_text(
            f"✅ <b>Fayl yuborildi</b>\n\nHajm: {_fmt_size(size)}",
            reply_markup=_back_log_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "LOG_DL_CUR", _APP_LOG.name, f"{_fmt_size(size)}")
    except Exception as exc:
        logger.exception("LOG_DL_CUR error: %s", exc)
        await q.message.edit_text(
            f"❌ Xato: <code>{exc}</code>",
            reply_markup=_back_log_kb(), parse_mode="HTML",
        )


# ════════════════════════════════════════════════════════════════════════════
# 📦 Download all logs (ZIP)
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_DL_ALL)
async def cb_log_dl_all(q: CallbackQuery) -> None:
    if not await _guard_cb(q):
        return
    await q.answer()

    log_files = [f for f in _all_log_files() if f.suffix != ".zip"]
    if not log_files:
        await q.message.edit_text(
            "📦 <b>Log fayllar topilmadi</b>\n\n"
            "Hali hech qanday log fayli yaratilmagan.",
            reply_markup=_back_log_kb(), parse_mode="HTML",
        )
        return

    total_size = sum(f.stat().st_size for f in log_files)
    await q.message.edit_text(
        f"⏳ <b>ZIP yaratilmoqda...</b>\n"
        f"{len(log_files)} fayl, jami {_fmt_size(total_size)}",
        parse_mode="HTML",
    )

    try:
        zip_path = await _zip_all_logs()
        zip_size = zip_path.stat().st_size

        if zip_size > 50 * 1024 * 1024:
            await q.message.edit_text(
                f"⚠️ <b>ZIP hajmi juda katta</b>: {_fmt_size(zip_size)}\n"
                f"Telegram chegarasi: 50 MB\n\n"
                f"Fayl saqlandi: <code>{zip_path.name}</code>",
                reply_markup=_back_log_kb(), parse_mode="HTML",
            )
            return

        doc     = FSInputFile(str(zip_path), filename=zip_path.name)
        caption = (
            f"📦 <b>{zip_path.name}</b>\n"
            f"Fayllar: {len(log_files)} | Hajm: {_fmt_size(zip_size)}\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await q.message.answer_document(doc, caption=caption, parse_mode="HTML")
        await q.message.edit_text(
            f"✅ <b>Barcha loglar yuborildi</b>\n\n"
            f"Fayllar: {len(log_files)} | ZIP: {_fmt_size(zip_size)}",
            reply_markup=_back_log_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "LOG_DL_ALL", zip_path.name, f"{_fmt_size(zip_size)}")
        zip_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.exception("LOG_DL_ALL error: %s", exc)
        await q.message.edit_text(
            f"❌ Xato: <code>{exc}</code>",
            reply_markup=_back_log_kb(), parse_mode="HTML",
        )


# ════════════════════════════════════════════════════════════════════════════
# 🗑 Clear logs — confirm → truncate
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == DEV_LOG_CLEAR)
async def cb_log_clear_preview(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(LogFSM.confirm_clear)
    await q.answer()

    info: list[str] = []
    total = 0
    for path in [_APP_LOG, _AI_LOG]:
        if path.exists():
            sz = path.stat().st_size
            total += sz
            info.append(f"• <code>{path.name}</code>: {_fmt_size(sz)}")
        else:
            info.append(f"• <code>{path.name}</code>: mavjud emas")

    await q.message.edit_text(
        "🗑 <b>Loglarni tozalash</b>\n\n"
        + "\n".join(info)
        + f"\n<b>Jami:</b> {_fmt_size(total)}\n\n"
        "Barcha log fayllar bo'shatiladi (o'chirilmaydi, faqat tozalanadi).\n"
        "<b>Bu amal qaytarib bo'lmaydi.</b>\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Ha, tozala",  callback_data=DEV_LOG_CLEAR_OK),
            InlineKeyboardButton(text="❌ Bekor",       callback_data=DEV_LOGS),
        ]]),
        parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == DEV_LOG_CLEAR_OK,
    StateFilter(LogFSM.confirm_clear),
)
async def cb_log_clear_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text("⏳ Tozalanmoqda...")

    cleared: list[str] = []
    errors:  list[str] = []
    freed = 0

    for path in [_APP_LOG, _AI_LOG]:
        if not path.exists():
            continue
        try:
            freed += path.stat().st_size
            path.write_text("", encoding="utf-8")
            cleared.append(path.name)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    result_lines = [f"✅ <b>Loglar tozalandi</b>\n"]
    if cleared:
        result_lines.append("Bo'shatildi: " + ", ".join(f"<code>{c}</code>" for c in cleared))
        result_lines.append(f"Bo'shatilgan joy: {_fmt_size(freed)}")
    if errors:
        result_lines.append("\n⚠️ Xatolar:")
        result_lines.extend(f"• <code>{e}</code>" for e in errors)

    await q.message.edit_text(
        "\n".join(result_lines),
        reply_markup=_back_log_kb(),
        parse_mode="HTML",
    )
    await log_action(
        q.from_user.id, "LOG_CLEAR",
        ",".join(cleared),
        f"freed={_fmt_size(freed)}" + (f" errors={len(errors)}" if errors else ""),
    )
