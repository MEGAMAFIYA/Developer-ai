"""Developer Mode › 🧪 Test Center

Features
────────
🗄 DB Test         — ikkala PostgreSQL pool ga ulanishni tekshirish
🌐 WebApp Test     — WebApp URL ga HTTP so'rov yuborish
🤖 Bot Test        — botdan o'z ma'lumotlarini olish
🏆 Score Test      — test natija qo'shish va tekshirish (keyin o'chirish)
✅ Barchasi        — barcha testlarni ketma-ket bajarish
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config as cfg
from database.global_db import get_global_pool
from database.game_db import get_game_pool, save_score
from handlers.developer.callbacks import (
    DEV_TEST,
    DEV_TEST_DB,
    DEV_TEST_WEB,
    DEV_TEST_BOT,
    DEV_TEST_SCORE,
    DEV_TEST_ALL,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:test")

_TG_MAX      = 4096
_TEST_USER   = 0          # dummy user_id for test scores
_TEST_GAME   = "__test__"


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _test_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗄 DB Test",      callback_data=DEV_TEST_DB),
            InlineKeyboardButton(text="🌐 WebApp Test",  callback_data=DEV_TEST_WEB),
        ],
        [
            InlineKeyboardButton(text="🤖 Bot Test",     callback_data=DEV_TEST_BOT),
            InlineKeyboardButton(text="🏆 Score Test",   callback_data=DEV_TEST_SCORE),
        ],
        [
            InlineKeyboardButton(text="✅ Barchasi",     callback_data=DEV_TEST_ALL),
            InlineKeyboardButton(text="⬅️ Orqaga",       callback_data="dev:menu"),
        ],
    ])


# ── Test runners ──────────────────────────────────────────────────────────────

async def _test_db() -> tuple[bool, str]:
    lines = ["🗄 <b>DB Test</b>\n"]
    ok_count = 0
    for label, get_pool_fn in [("Global DB", get_global_pool), ("Game DB", get_game_pool)]:
        try:
            pool = await get_pool_fn()
            val  = await pool.fetchval("SELECT 1")
            assert val == 1
            lines.append(f"  ✅ {label}: bogliq")
            ok_count += 1
        except Exception as exc:
            lines.append(f"  ❌ {label}: {exc}")
    passed = ok_count == 2
    lines.append(f"\n{'✅ Barcha DB testlari o`tdi' if passed else '⚠️ Ba`zi testlar muvaffaqiyatsiz'}")
    return passed, "\n".join(lines)


async def _test_web() -> tuple[bool, str]:
    lines = ["🌐 <b>WebApp Test</b>\n"]
    url   = cfg.config.WEBAPP_URL
    lines.append(f"URL: <code>{url}</code>")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                status = resp.status
                ok     = status < 400
                lines.append(f"  {'✅' if ok else '❌'} HTTP {status}")
                return ok, "\n".join(lines)
    except Exception as exc:
        lines.append(f"  ❌ Xato: {exc}")
        return False, "\n".join(lines)


async def _test_bot(bot) -> tuple[bool, str]:
    lines = ["🤖 <b>Bot Test</b>\n"]
    try:
        me = await bot.get_me()
        lines += [
            f"  ✅ Bot ishlayapti",
            f"  ID:       <code>{me.id}</code>",
            f"  Username: @{me.username}",
            f"  Nomi:     {me.full_name}",
        ]
        return True, "\n".join(lines)
    except Exception as exc:
        lines.append(f"  ❌ Bot xatosi: {exc}")
        return False, "\n".join(lines)


async def _test_score() -> tuple[bool, str]:
    lines = ["🏆 <b>Score Test</b>\n"]
    try:
        # Insert
        result = await save_score(
            user_id=_TEST_USER,
            username="test_user",
            first_name="Test",
            game_name=_TEST_GAME,
            score=9999,
        )
        lines.append(f"  ✅ Insert: score={result['row']['score']}, rank={result['rank']}")

        # Read back
        pool = await get_game_pool()
        val  = await pool.fetchval(
            "SELECT score FROM scores WHERE user_id=$1 AND game_name=$2 ORDER BY id DESC LIMIT 1",
            _TEST_USER, _TEST_GAME,
        )
        assert val == 9999, f"Read mismatch: {val}"
        lines.append("  ✅ Read: tasdiqlandi")

        # Cleanup
        deleted = await pool.fetchval(
            "DELETE FROM scores WHERE user_id=$1 AND game_name=$2 RETURNING id",
            _TEST_USER, _TEST_GAME,
        )
        lines.append(f"  ✅ Cleanup: o'chirildi (id={deleted})")
        lines.append("\n✅ Score pipeline ishlayapti")
        return True, "\n".join(lines)
    except Exception as exc:
        lines.append(f"  ❌ Xato: {exc}")
        # Attempt cleanup silently
        try:
            pool = await get_game_pool()
            await pool.execute(
                "DELETE FROM scores WHERE user_id=$1 AND game_name=$2",
                _TEST_USER, _TEST_GAME,
            )
        except Exception:
            pass
        return False, "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_TEST)
async def cb_test_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🧪 <b>Test Center</b>\n\nQuyidagi testlardan birini tanlang:",
        reply_markup=_test_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_TEST_DB)
async def cb_test_db(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Tekshirilmoqda…")
    ok, text = await _test_db()
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_test_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_TEST_WEB)
async def cb_test_web(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Tekshirilmoqda…")
    ok, text = await _test_web()
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_test_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_TEST_BOT)
async def cb_test_bot(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Tekshirilmoqda…")
    ok, text = await _test_bot(q.bot)
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_test_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_TEST_SCORE)
async def cb_test_score(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Test bajarilmoqda…")
    ok, text = await _test_score()
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_test_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_TEST_ALL)
async def cb_test_all(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Barcha testlar bajarilmoqda…")

    db_ok,    db_txt    = await _test_db()
    web_ok,   web_txt   = await _test_web()
    bot_ok,   bot_txt   = await _test_bot(q.bot)
    score_ok, score_txt = await _test_score()

    total  = 4
    passed = sum([db_ok, web_ok, bot_ok, score_ok])
    icon   = "✅" if passed == total else "⚠️" if passed > 0 else "❌"

    summary = (
        f"🧪 <b>Test natijalari: {icon} {passed}/{total}</b>\n\n"
        + "\n\n".join([db_txt, web_txt, bot_txt, score_txt])
    )

    await log_action(
        q.from_user.id, "TEST_ALL",
        f"passed={passed}/{total}",
        "ok" if passed == total else "partial",
    )

    await q.message.edit_text(
        summary[:_TG_MAX], reply_markup=_test_keyboard(), parse_mode="HTML"
    )
