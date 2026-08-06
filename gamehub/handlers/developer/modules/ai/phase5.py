"""AI Developer — Phase 5: Advanced AI Features

Replaces the eight COMING_SOON stubs that were in handlers.py.

Features
────────
🧩 AI Code Assistant    — shortcuts to all code tools + save-to-file
🪄 AI Game Builder      — describe → generate full HTML5 game → save to webapp
🎮 AI Gameplay Designer — select game → describe change → AI patches JS → save
🎨 AI UI Designer       — select game → describe UI → AI patches CSS → save
🖼 AI Asset Generator   — describe sprite → AI generates SVG → save
📦 AI Assets Manager    — upload / delete non-HTML files in webapp/games/
👁 AI Preview           — live WebApp URLs for all active games
🧪 AI Test Center       — AI review + validation of HTML5 code

Architecture
────────────
• All AI calls go through services.py (never imports providers directly).
• FSM state groups are defined in states.py; imported here.
• New callback constants are in callbacks.py.
• This router is included last in __init__.py — no conflicts with earlier routers.
• Long AI results (game HTML) are stored in FSM MemoryStorage for save step.
• Every file-write action is logged via action_log.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

import config as cfg
from database.global_db import get_all_games, add_game
from handlers.developer.modules.ai.callbacks import (
    AI_MENU, AI_CANCEL,
    # Phase 5 entry points (stub replacements)
    AI_CODE, AI_BUILDER, AI_GAMEPLAY, AI_DESIGN,
    AI_IMAGE, AI_ASSETS, AI_PREVIEW, AI_TEST,
    # Phase 5 sub-actions
    AI_CODE_SAVE,
    AI_BUILDER_SAVE, AI_BUILDER_DISCARD,
    AI_GAMEPLAY_LIST, AI_GAMEPLAY_SAVE_OK, AI_GAMEPLAY_DISCARD,
    AI_DESIGN_LIST, AI_DESIGN_SAVE_OK, AI_DESIGN_DISCARD,
    AI_IMAGE_SAVE, AI_IMAGE_DISCARD,
    AI_ASSETS_LIST, AI_ASSETS_UPLOAD, AI_ASSETS_DEL_OK, AI_ASSETS_DEL_NO,
    AI_PREVIEW_LIST,
    AI_TEST_CODE, AI_TEST_FILE,
    # Phase 3 — reused by Code Assistant keyboard
    AI_WRITE_CODE, AI_EDIT_CODE, AI_ANALYZE_CODE, AI_FIND_BUG, AI_FIX_BUG,
)
from handlers.developer.modules.ai.menu import (
    ai_back_keyboard, ai_menu_keyboard, AI_MENU_TEXT,
)
from handlers.developer.modules.ai.states import (
    AIBuilderStates, AIGameplayStates, AIDesignStates,
    AIAssetStates, AICodeSaveStates, AITestStates,
    AIAssetManagerFSM,
)
from handlers.developer.modules.ai import services
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:phase5")

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE      = Path(__file__).resolve().parents[3]   # gamehub/
_GAMES_DIR = _BASE / "webapp" / "games"
_TG_MAX    = 4096

# Dynamic callback prefixes (matched with startswith in filters)
_GAMEPLAY_SEL = "ai:gameplay:sel:"
_DESIGN_SEL   = "ai:design:sel:"
_ASSETS_DEL   = "ai:assets:del:"
_PREVIEW_GAME = "ai:preview:game:"
_TEST_SEL     = "ai:test:sel:"

# Asset file extensions managed by Assets Manager
_ASSET_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif",
    ".mp3", ".ogg", ".wav",
    ".json", ".css", ".js",
}


# ── Guards ────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


async def _guard_msg(m: Message) -> bool:
    if _is_admin(m.from_user.id):
        return True
    await m.answer("⛔ Ruxsat yo'q.")
    return False


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=AI_CANCEL),
    ]])


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


def _esc(s: str) -> str:
    """Escape HTML special chars for use inside <pre> blocks."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _load_game_code(html_file: str) -> str | None:
    path = _GAMES_DIR / html_file
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")[:12000]


def _safe_filename(name: str, default_ext: str = ".html") -> str:
    """Strip path components; ensure a safe extension."""
    name = Path(name).name  # strip any directory component
    if "." not in name:
        name += default_ext
    return name


async def _game_list_kb(prefix: str) -> tuple[str, InlineKeyboardMarkup]:
    """Return (prompt_text, keyboard) showing all games as selection buttons."""
    games = await get_all_games(only_active=False)
    if not games:
        return (
            "⚠️ O'yinlar topilmadi.",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU),
            ]]),
        )
    rows = [
        [InlineKeyboardButton(
            text=f"{'✅' if g.get('active') else '❌'} {g['name']}",
            callback_data=f"{prefix}{g['slug']}",
        )]
        for g in games
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU)])
    return f"🎮 O'yinni tanlang ({len(games)} ta):", InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_code_result(
    message: Message,
    full_code: str,
    title: str,
    save_cb: str,
    discard_cb: str,
    extra: str = "",
) -> None:
    """Show a (possibly truncated) AI code result with Save / Discard buttons."""
    preview   = _esc(full_code[:2400])
    truncated = len(full_code) > 2400
    header    = f"✅ <b>{title}</b>"
    if extra:
        header += f"\n{extra}"
    if truncated:
        header += f"\n<i>({len(full_code):,} belgi — birinchi 2400 ko'rsatilmoqda)</i>"

    await message.answer(
        f"{header}\n\n<pre>{preview}</pre>\n\n💾 Faylga saqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💾 Ha, saqlash", callback_data=save_cb),
            InlineKeyboardButton(text="🗑 Bekor",        callback_data=discard_cb),
        ]]),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. AI Code Assistant  (AI_CODE)
# ══════════════════════════════════════════════════════════════════════════════

def _code_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Kod yozdirish",    callback_data=AI_WRITE_CODE),
            InlineKeyboardButton(text="✏️ Kodni tahrirlash", callback_data=AI_EDIT_CODE),
        ],
        [
            InlineKeyboardButton(text="🔍 Kodni tahlil",     callback_data=AI_ANALYZE_CODE),
            InlineKeyboardButton(text="🧠 Bug topish",       callback_data=AI_FIND_BUG),
        ],
        [
            InlineKeyboardButton(text="❌ Xatoni tuzatish",  callback_data=AI_FIX_BUG),
            InlineKeyboardButton(text="💾 Faylga saqlash",   callback_data=AI_CODE_SAVE),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU)],
    ])


@router.callback_query(lambda c: c.data == AI_CODE)
async def cb_ai_code(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    status = services.get_ai_status()
    prov = status["provider"] or "sozlanmagan"
    await q.message.edit_text(
        f"🧩 <b>AI Code Assistant</b>\n\n"
        f"Provider: <code>{prov}</code>\n\n"
        "HTML5 o'yinlar uchun kod yozish, tahrirlash, tahlil va saqlash.\n\n"
        "<i>Kerakli amalni tanlang:</i>",
        reply_markup=_code_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_CODE_SAVE)
async def cb_code_save_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.set_state(AICodeSaveStates.waiting_code)
    await q.message.edit_text(
        "💾 <b>Kodni faylga saqlash — 1/2</b>\n\n"
        "Saqlash kerak bo'lgan kodni yuboring (HTML, JS, CSS).\n"
        "<i>Butun fayl mazmunini ko'chiring va yuboring.</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AICodeSaveStates.waiting_code))
async def msg_code_save_receive(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    code = (m.text or "").strip()
    if not code:
        await m.answer("⚠️ Kod bo'sh. Iltimos kodni yuboring.")
        return
    await state.update_data(code=code)
    await state.set_state(AICodeSaveStates.waiting_filename)
    await m.answer(
        "💾 <b>Kodni faylga saqlash — 2/2</b>\n\n"
        "Fayl nomini kiriting (masalan: <code>mening_oyinim.html</code>).\n"
        "Fayl <code>webapp/games/</code> ga saqlanadi.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AICodeSaveStates.waiting_filename))
async def msg_code_save_filename(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    raw      = (m.text or "").strip()
    filename = _safe_filename(raw, ".html")
    if "/" in raw or "\\" in raw:
        await m.answer("⛔ Fayl nomida / yoki \\ bo'lmasin.")
        return
    data = await state.get_data()
    code = data.get("code", "")
    await state.clear()
    _GAMES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _GAMES_DIR / filename
    try:
        dest.write_text(code, encoding="utf-8")
        await log_action(
            m.from_user.id, "CODE_SAVE", filename,
            f"size={_fmt_size(dest.stat().st_size)}",
        )
        await m.answer(
            f"✅ <b>{filename}</b> saqlandi!\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}\n"
            f"Joylashuv: <code>webapp/games/{filename}</code>",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("code save error: %s", exc)
        await m.answer(f"❌ Xato: {exc}", reply_markup=ai_back_keyboard())


# ══════════════════════════════════════════════════════════════════════════════
# 2. AI Game Builder  (AI_BUILDER)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_BUILDER)
async def cb_ai_builder(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await state.set_state(AIBuilderStates.waiting_description)
    await q.answer()
    await q.message.edit_text(
        "🪄 <b>AI Game Builder</b>\n\n"
        "O'yin g'oyasini batafsil tasvirlab bering.\n"
        "AI bitta HTML faylda to'liq ishlaydigan HTML5 canvas o'yini yaratib beradi.\n\n"
        "<i>Misol: «Kosmosda uchayotgan kema boshqaramiz. Meteoritlardan "
        "qochamiz, o'q otamiz. Har 10 to'siqdan so'ng tezlik oshadi. "
        "Touch boshqaruv bo'lsin.»</i>\n\n"
        "⏱ Yaratish 30–90 soniya olishi mumkin.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIBuilderStates.waiting_description))
async def msg_builder_description(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    description = (m.text or "").strip()
    if not description:
        await m.answer("⚠️ Tavsif bo'sh.")
        return
    sent = await m.answer(
        "⏳ <b>AI Game Builder</b> — O'yin yaratilmoqda, kuting…",
        parse_mode="HTML",
    )
    result = await services.ai_create_game(description)
    if not result.ok:
        await state.clear()
        await sent.edit_text(
            f"❌ <b>Xato</b>\n\n<code>{_esc(result.error or 'Noma`lum xato')}</code>",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
        return
    await state.update_data(game_code=result.content, description=description)
    await state.set_state(AIBuilderStates.pending_save)
    await sent.delete()
    await _show_code_result(
        m, result.content,
        "O'yin muvaffaqiyatli yaratildi!",
        AI_BUILDER_SAVE, AI_BUILDER_DISCARD,
        f"Provider: <code>{result.provider}</code>",
    )


@router.callback_query(
    StateFilter(AIBuilderStates.pending_save),
    lambda c: c.data == AI_BUILDER_SAVE,
)
async def cb_builder_save_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.set_state(AIBuilderStates.waiting_filename)
    await q.message.edit_text(
        "💾 <b>O'yinni saqlash</b>\n\n"
        "Fayl nomini kiriting (masalan: <code>space_shooter.html</code>).\n"
        "• Fayl <code>webapp/games/</code> ga saqlanadi.\n"
        "• O'yin DB ga <b>nofaol</b> holda qo'shiladi.\n"
        "• Faollashtirish: Developer → O'yinlar → toggle.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIBuilderStates.waiting_filename))
async def msg_builder_filename(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    raw      = (m.text or "").strip()
    filename = _safe_filename(raw, ".html")
    if "/" in raw or "\\" in raw:
        await m.answer("⛔ Fayl nomida / yoki \\ bo'lmasin.")
        return
    data = await state.get_data()
    game_code   = data.get("game_code", "")
    description = data.get("description", "")
    await state.clear()
    _GAMES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _GAMES_DIR / filename
    try:
        dest.write_text(game_code, encoding="utf-8")
        slug = re.sub(r"[^a-z0-9_]", "_", filename.replace(".html", "").lower())
        await add_game(
            slug=slug,
            name=f"🎮 {slug.replace('_', ' ').title()}",
            description=description[:200],
            html_file=filename,
            category="arcade",
            active=False,
        )
        await log_action(
            m.from_user.id, "GAME_BUILD", filename,
            f"size={_fmt_size(dest.stat().st_size)}",
        )
        await m.answer(
            f"✅ <b>{filename}</b> saqlandi!\n\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}\n"
            f"Slug: <code>{slug}</code>\n\n"
            "⚠️ O'yin hozir <b>nofaol</b>. "
            "Faollashtirish: Developer → O'yinlar → toggle.",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("builder save: %s", exc)
        await m.answer(f"❌ Saqlashda xato: {exc}", reply_markup=ai_back_keyboard())


@router.callback_query(
    StateFilter(AIBuilderStates.pending_save),
    lambda c: c.data == AI_BUILDER_DISCARD,
)
async def cb_builder_discard(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    await q.message.edit_text(AI_MENU_TEXT, reply_markup=ai_menu_keyboard(), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# 3. AI Gameplay Designer  (AI_GAMEPLAY)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data in (AI_GAMEPLAY, AI_GAMEPLAY_LIST))
async def cb_ai_gameplay(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    list_text, kb = await _game_list_kb(_GAMEPLAY_SEL)
    await q.message.edit_text(
        "🎮 <b>AI Gameplay Designer</b>\n\n"
        "O'yin mexanikasi, tezligi yoki qoidalarini o'zgartirish.\n\n"
        + list_text,
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith(_GAMEPLAY_SEL))
async def cb_gameplay_select(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    slug  = q.data[len(_GAMEPLAY_SEL):]
    games = await get_all_games(only_active=False)
    game  = next((g for g in games if g["slug"] == slug), None)
    if not game:
        await q.answer("O'yin topilmadi.", show_alert=True)
        return
    code = _load_game_code(game["html_file"])
    if code is None:
        await q.answer(f"Fayl topilmadi: {game['html_file']}", show_alert=True)
        return
    await q.answer()
    await state.update_data(
        slug=slug, html_file=game["html_file"],
        game_name=game["name"], game_code=code,
    )
    await state.set_state(AIGameplayStates.waiting_change)
    await q.message.edit_text(
        f"🎮 <b>Gameplay Designer — {game['name']}</b>\n\n"
        f"Fayl: <code>{game['html_file']}</code> ({_fmt_size(len(code.encode()))})\n\n"
        "O'yin mexanikasida nima o'zgartirish kerakligini yozing:\n\n"
        "<i>Misol: «Tezlikni 2 barobarga oshir, jonlar sonini 5 taga chiqar»</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIGameplayStates.waiting_change))
async def msg_gameplay_change(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    instruction = (m.text or "").strip()
    if not instruction:
        await m.answer("⚠️ Ko'rsatma bo'sh.")
        return
    data = await state.get_data()
    sent = await m.answer(
        f"⏳ <b>Gameplay Designer</b> — {data.get('game_name', '')} o'zgartirilmoqda…",
        parse_mode="HTML",
    )
    result = await services.ai_gameplay_change(data["game_code"], instruction)
    if not result.ok:
        await state.clear()
        await sent.edit_text(
            f"❌ <b>Xato</b>\n\n<code>{_esc(result.error or 'Noma`lum xato')}</code>",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
        return
    await state.update_data(new_code=result.content)
    await state.set_state(AIGameplayStates.confirm_save)
    await sent.delete()
    await _show_code_result(
        m, result.content,
        f"{data['game_name']} yangilandi!",
        AI_GAMEPLAY_SAVE_OK, AI_GAMEPLAY_DISCARD,
        f"Fayl: <code>{data['html_file']}</code>",
    )


@router.callback_query(lambda c: c.data == AI_GAMEPLAY_SAVE_OK)
async def cb_gameplay_save(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data = await state.get_data()
    new_code  = data.get("new_code", "")
    html_file = data.get("html_file", "")
    game_name = data.get("game_name", "")
    if not new_code or not html_file:
        await q.answer("Ma'lumot topilmadi. Qaytadan urinib ko'ring.", show_alert=True)
        await state.clear()
        return
    await state.clear()
    dest = _GAMES_DIR / html_file
    try:
        dest.write_text(new_code, encoding="utf-8")
        await log_action(q.from_user.id, "GAMEPLAY_SAVE", html_file, f"size={_fmt_size(dest.stat().st_size)}")
        await q.answer("✅ Saqlandi!")
        await q.message.edit_text(
            f"✅ <b>{game_name}</b> muvaffaqiyatli yangilandi!\n"
            f"Fayl: <code>webapp/games/{html_file}</code>\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        await q.message.edit_text(
            f"❌ Saqlashda xato: {exc}", reply_markup=ai_back_keyboard()
        )


@router.callback_query(lambda c: c.data == AI_GAMEPLAY_DISCARD)
async def cb_gameplay_discard(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    await q.message.edit_text(AI_MENU_TEXT, reply_markup=ai_menu_keyboard(), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# 4. AI UI Designer  (AI_DESIGN)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data in (AI_DESIGN, AI_DESIGN_LIST))
async def cb_ai_design(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    list_text, kb = await _game_list_kb(_DESIGN_SEL)
    await q.message.edit_text(
        "🎨 <b>AI UI Designer</b>\n\n"
        "O'yinning vizual qismini (ranglar, shriftlar, UI elementlar) o'zgartirish.\n\n"
        + list_text,
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith(_DESIGN_SEL))
async def cb_design_select(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    slug  = q.data[len(_DESIGN_SEL):]
    games = await get_all_games(only_active=False)
    game  = next((g for g in games if g["slug"] == slug), None)
    if not game:
        await q.answer("O'yin topilmadi.", show_alert=True)
        return
    code = _load_game_code(game["html_file"])
    if code is None:
        await q.answer(f"Fayl topilmadi: {game['html_file']}", show_alert=True)
        return
    await q.answer()
    await state.update_data(
        slug=slug, html_file=game["html_file"],
        game_name=game["name"], game_code=code,
    )
    await state.set_state(AIDesignStates.waiting_change)
    await q.message.edit_text(
        f"🎨 <b>UI Designer — {game['name']}</b>\n\n"
        f"Fayl: <code>{game['html_file']}</code>\n\n"
        "Dizayn o'zgartirishni tasvirlab bering:\n\n"
        "<i>Misol: «Fon rangini quyuq ko'k qil, "
        "o'yin maydoni chegarasini yashil rang, "
        "yirikroq shrift ishlat»</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIDesignStates.waiting_change))
async def msg_design_change(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    instruction = (m.text or "").strip()
    if not instruction:
        await m.answer("⚠️ Ko'rsatma bo'sh.")
        return
    data = await state.get_data()
    sent = await m.answer(
        f"⏳ <b>UI Designer</b> — {data.get('game_name', '')} dizayni o'zgartirilmoqda…",
        parse_mode="HTML",
    )
    result = await services.ai_design_ui(data["game_code"], instruction)
    if not result.ok:
        await state.clear()
        await sent.edit_text(
            f"❌ <b>Xato</b>\n\n<code>{_esc(result.error or 'Noma`lum xato')}</code>",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
        return
    await state.update_data(new_code=result.content)
    await state.set_state(AIDesignStates.confirm_save)
    await sent.delete()
    await _show_code_result(
        m, result.content,
        f"{data['game_name']} dizayni yangilandi!",
        AI_DESIGN_SAVE_OK, AI_DESIGN_DISCARD,
        f"Fayl: <code>{data['html_file']}</code>",
    )


@router.callback_query(lambda c: c.data == AI_DESIGN_SAVE_OK)
async def cb_design_save(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data = await state.get_data()
    new_code  = data.get("new_code", "")
    html_file = data.get("html_file", "")
    game_name = data.get("game_name", "")
    if not new_code or not html_file:
        await q.answer("Ma'lumot topilmadi. Qaytadan urinib ko'ring.", show_alert=True)
        await state.clear()
        return
    await state.clear()
    dest = _GAMES_DIR / html_file
    try:
        dest.write_text(new_code, encoding="utf-8")
        await log_action(q.from_user.id, "DESIGN_SAVE", html_file, f"size={_fmt_size(dest.stat().st_size)}")
        await q.answer("✅ Saqlandi!")
        await q.message.edit_text(
            f"✅ <b>{game_name}</b> dizayni muvaffaqiyatli yangilandi!\n"
            f"Fayl: <code>webapp/games/{html_file}</code>\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        await q.message.edit_text(
            f"❌ Saqlashda xato: {exc}", reply_markup=ai_back_keyboard()
        )


@router.callback_query(lambda c: c.data == AI_DESIGN_DISCARD)
async def cb_design_discard(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    await q.message.edit_text(AI_MENU_TEXT, reply_markup=ai_menu_keyboard(), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# 5. AI Asset Generator  (AI_IMAGE)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_IMAGE)
async def cb_ai_image(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await state.set_state(AIAssetStates.waiting_description)
    await q.answer()
    await q.message.edit_text(
        "🖼 <b>AI Asset Generator</b>\n\n"
        "O'yin uchun SVG grafika (sprite, belgi, fon elementi) yaratish.\n\n"
        "Kerakli rasmni tasvirlab bering:\n\n"
        "<i>Misol: «Kosmik kema — kichik geometrik, uchburchak asosli korpus, "
        "2 ta qanot, alangali dvigatel»</i>\n\n"
        "<i>Misol: «Oltin tanga — doira, yaltiroq sariq rang, ichida ¥ belgisi»</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIAssetStates.waiting_description))
async def msg_asset_description(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    description = (m.text or "").strip()
    if not description:
        await m.answer("⚠️ Tavsif bo'sh.")
        return
    sent = await m.answer(
        "⏳ <b>Asset Generator</b> — SVG yaratilmoqda…", parse_mode="HTML"
    )
    result = await services.ai_generate_svg(description)
    if not result.ok:
        await state.clear()
        await sent.edit_text(
            f"❌ <b>Xato</b>\n\n<code>{_esc(result.error or 'Noma`lum xato')}</code>",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
        return
    await state.update_data(svg_code=result.content)
    await state.set_state(AIAssetStates.pending_save)
    await sent.delete()
    # Show preview (SVG is typically short)
    preview = _esc(result.content[:1800])
    await m.answer(
        f"✅ <b>SVG tayyor!</b>\n\n<pre>{preview}</pre>\n\n"
        "💾 SVG faylni saqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💾 Ha, saqlash",  callback_data=AI_IMAGE_SAVE),
            InlineKeyboardButton(text="🗑 Bekor",        callback_data=AI_IMAGE_DISCARD),
        ]]),
        parse_mode="HTML",
    )


@router.callback_query(
    StateFilter(AIAssetStates.pending_save),
    lambda c: c.data == AI_IMAGE_SAVE,
)
async def cb_image_save_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.set_state(AIAssetStates.waiting_filename)
    await q.message.edit_text(
        "💾 <b>SVG saqlash</b>\n\n"
        "Fayl nomini kiriting (masalan: <code>kema.svg</code>).\n"
        "Fayl <code>webapp/games/</code> ga saqlanadi.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIAssetStates.waiting_filename))
async def msg_asset_filename(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    raw      = (m.text or "").strip()
    filename = _safe_filename(raw, ".svg")
    if "/" in raw or "\\" in raw:
        await m.answer("⛔ Fayl nomida / yoki \\ bo'lmasin.")
        return
    data     = await state.get_data()
    svg_code = data.get("svg_code", "")
    await state.clear()

    # Strip markdown fences if AI wrapped SVG in ```svg ... ```
    match = re.search(r"```(?:svg|xml)?\s*\n?(.*?)\n?```", svg_code, re.DOTALL | re.IGNORECASE)
    clean = match.group(1).strip() if match else svg_code.strip()

    _GAMES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _GAMES_DIR / filename
    try:
        dest.write_text(clean, encoding="utf-8")
        await log_action(
            m.from_user.id, "ASSET_SAVE", filename,
            f"size={_fmt_size(dest.stat().st_size)}",
        )
        await m.answer(
            f"✅ <b>{filename}</b> saqlandi!\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}\n"
            f"Joylashuv: <code>webapp/games/{filename}</code>",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        await m.answer(f"❌ Xato: {exc}", reply_markup=ai_back_keyboard())


@router.callback_query(
    StateFilter(AIAssetStates.pending_save),
    lambda c: c.data == AI_IMAGE_DISCARD,
)
async def cb_image_discard(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    await q.message.edit_text(AI_MENU_TEXT, reply_markup=ai_menu_keyboard(), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# 6. AI Assets Manager  (AI_ASSETS)
# ══════════════════════════════════════════════════════════════════════════════

def _list_assets() -> list[str]:
    if not _GAMES_DIR.exists():
        return []
    return sorted(
        f.name for f in _GAMES_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in _ASSET_EXTS
    )


def _assets_kb(assets: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=f"📄 {name}", callback_data=f"ai:asset:noop"),
            InlineKeyboardButton(text="🗑",           callback_data=f"{_ASSETS_DEL}{name}"),
        ]
        for name in assets[:20]
    ]
    rows += [
        [InlineKeyboardButton(text="📤 Asset yuklash", callback_data=AI_ASSETS_UPLOAD)],
        [
            InlineKeyboardButton(text="🔄 Yangilash",  callback_data=AI_ASSETS_LIST),
            InlineKeyboardButton(text="⬅️ Orqaga",    callback_data=AI_MENU),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda c: c.data in (AI_ASSETS, AI_ASSETS_LIST))
async def cb_ai_assets(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    assets = _list_assets()
    text = (
        f"📦 <b>AI Assets Manager</b> ({len(assets)} fayl)\n\n"
        f"<code>webapp/games/</code>\n"
        + ("" if assets else "\n⚠️ Hech qanday asset fayl topilmadi.")
    )
    await q.message.edit_text(
        text, reply_markup=_assets_kb(assets), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data.startswith(_ASSETS_DEL))
async def cb_asset_del_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    filename = q.data[len(_ASSETS_DEL):]
    path = _GAMES_DIR / filename
    if not path.exists():
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer()
    await state.set_state(AIAssetManagerFSM.pending_delete)
    await state.update_data(filename=filename)
    await q.message.edit_text(
        f"🗑 <b>O'chirishni tasdiqlang</b>\n\n"
        f"Fayl: <code>{filename}</code> ({_fmt_size(path.stat().st_size)})\n\n"
        "⚠️ Bu amalni qaytarib bo'lmaydi!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Ha, o'chir", callback_data=AI_ASSETS_DEL_OK),
            InlineKeyboardButton(text="❌ Bekor",       callback_data=AI_ASSETS_DEL_NO),
        ]]),
        parse_mode="HTML",
    )


@router.callback_query(
    StateFilter(AIAssetManagerFSM.pending_delete),
    lambda c: c.data == AI_ASSETS_DEL_OK,
)
async def cb_asset_del_ok(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data     = await state.get_data()
    filename = data.get("filename", "")
    await state.clear()
    path = _GAMES_DIR / filename
    try:
        size = path.stat().st_size if path.exists() else 0
        path.unlink(missing_ok=True)
        await log_action(q.from_user.id, "ASSET_DELETE", filename, f"size={size}")
        await q.answer(f"✅ {filename} o'chirildi")
    except Exception as exc:
        await q.answer(f"❌ Xato: {exc}", show_alert=True)
        return
    assets = _list_assets()
    await q.message.edit_text(
        f"📦 <b>AI Assets Manager</b> ({len(assets)} fayl)\n<code>webapp/games/</code>",
        reply_markup=_assets_kb(assets),
        parse_mode="HTML",
    )


@router.callback_query(
    StateFilter(AIAssetManagerFSM.pending_delete),
    lambda c: c.data == AI_ASSETS_DEL_NO,
)
async def cb_asset_del_no(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor")
    assets = _list_assets()
    await q.message.edit_text(
        f"📦 <b>AI Assets Manager</b> ({len(assets)} fayl)",
        reply_markup=_assets_kb(assets),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_ASSETS_UPLOAD)
async def cb_asset_upload_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.set_state(AIAssetManagerFSM.waiting_upload)
    exts = " · ".join(sorted(_ASSET_EXTS))
    await q.message.edit_text(
        "📤 <b>Asset yuklash</b>\n\n"
        "Faylni <b>document</b> sifatida yuboring.\n\n"
        f"Ruxsat etilgan formatlar:\n<code>{exts}</code>\n\n"
        "Fayl <code>webapp/games/</code> ga saqlanadi.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AIAssetManagerFSM.waiting_upload), F.document)
async def msg_asset_upload(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    doc      = m.document
    filename = doc.file_name or "asset"
    ext      = Path(filename).suffix.lower()
    if ext not in _ASSET_EXTS:
        await m.answer(
            f"⛔ Ruxsat etilgan formatlar: {' '.join(sorted(_ASSET_EXTS))}",
            reply_markup=ai_back_keyboard(),
        )
        return
    _GAMES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _GAMES_DIR / filename
    try:
        await m.bot.download(doc, destination=str(dest))
        await log_action(
            m.from_user.id, "ASSET_UPLOAD", filename,
            f"size={_fmt_size(dest.stat().st_size)}",
        )
        await m.answer(
            f"✅ <b>{filename}</b> muvaffaqiyatli yuklandi!\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("asset upload: %s", exc)
        await m.answer(f"❌ Yuklashda xato: {exc}", reply_markup=ai_back_keyboard())


@router.message(StateFilter(AIAssetManagerFSM.waiting_upload))
async def msg_asset_upload_wrong(m: Message) -> None:
    if not _is_admin(m.from_user.id):
        return
    await m.answer(
        "⚠️ Faylni <b>document</b> sifatida yuboring.", parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7. AI Preview  (AI_PREVIEW)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data in (AI_PREVIEW, AI_PREVIEW_LIST))
async def cb_ai_preview(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    games      = await get_all_games(only_active=False)
    webapp_url = cfg.config.WEBAPP_URL.rstrip("/")
    if not games:
        await q.message.edit_text(
            "👁 <b>Preview</b>\n\nHech qanday o'yin topilmadi.",
            reply_markup=ai_back_keyboard(),
            parse_mode="HTML",
        )
        return
    rows = [
        [InlineKeyboardButton(
            text=f"{'✅' if g.get('active') else '❌'} {g['name']}",
            web_app=WebAppInfo(url=f"{webapp_url}/games/{g['html_file']}"),
        )]
        for g in games
    ]
    rows.append([
        InlineKeyboardButton(text="🔄 Yangilash", callback_data=AI_PREVIEW_LIST),
        InlineKeyboardButton(text="⬅️ Orqaga",   callback_data=AI_MENU),
    ])
    await q.message.edit_text(
        f"👁 <b>Preview</b> ({len(games)} ta o'yin)\n\n"
        f"Base URL: <code>{webapp_url}</code>\n\n"
        "Tugmani bosib o'yinni to'g'ridan-to'g'ri oching:\n"
        "(✅ = faol, ❌ = nofaol)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 8. AI Test Center  (AI_TEST)
# ══════════════════════════════════════════════════════════════════════════════

def _test_center_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧪 Kodni test qil",   callback_data=AI_TEST_CODE),
            InlineKeyboardButton(text="🎮 O'yin faylini test", callback_data=AI_TEST_FILE),
        ],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=AI_MENU)],
    ])


@router.callback_query(lambda c: c.data == AI_TEST)
async def cb_ai_test(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    status = services.get_ai_status()
    prov   = status["provider"] or "sozlanmagan"
    await q.message.edit_text(
        f"🧪 <b>AI Test Center</b>\n\n"
        f"Provider: <code>{prov}</code>\n\n"
        "HTML5 o'yin kodini AI yordamida tekshirish va baholash.\n\n"
        "AI tekshiradigan narsalar:\n"
        "• ✅ HTML tuzilishi\n"
        "• ✅ JavaScript sintaksisi\n"
        "• ✅ Canvas API\n"
        "• ✅ Telegram WebApp SDK\n"
        "• ⚠️ Potensial muammolar\n"
        "• 💡 Yaxshilash tavsiyalari",
        reply_markup=_test_center_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == AI_TEST_CODE)
async def cb_test_code_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await state.set_state(AITestStates.waiting_code)
    await q.answer()
    await q.message.edit_text(
        "🧪 <b>Kodni test qilish</b>\n\n"
        "Tekshirilishi kerak bo'lgan HTML5 kodini yuboring.\n"
        "<i>Butun HTML faylni yoki kod parchani yuboring.</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(StateFilter(AITestStates.waiting_code))
async def msg_test_code(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    code = (m.text or "").strip()
    if not code:
        await m.answer("⚠️ Kod bo'sh.")
        return
    await state.clear()
    sent   = await m.answer("⏳ <b>AI Test Center</b> — Kod tekshirilmoqda…", parse_mode="HTML")
    result = await services.ai_validate_code(code)
    if result.ok:
        body = f"🧪 <b>Test natijasi</b>\n\n{result.content}"
        if len(body) <= _TG_MAX:
            await sent.edit_text(body, reply_markup=_test_center_kb(), parse_mode="HTML")
        else:
            await sent.delete()
            for i in range(0, len(body), _TG_MAX):
                chunk = body[i: i + _TG_MAX]
                kb    = _test_center_kb() if i + _TG_MAX >= len(body) else None
                await m.answer(chunk, reply_markup=kb, parse_mode="HTML")
        await log_action(m.from_user.id, "AI_TEST", f"{len(code)} belgi", "ok")
    else:
        await sent.edit_text(
            f"❌ <b>Test xatosi</b>\n\n<code>{_esc(result.error or 'Noma`lum xato')}</code>",
            reply_markup=_test_center_kb(),
            parse_mode="HTML",
        )


@router.callback_query(lambda c: c.data == AI_TEST_FILE)
async def cb_test_file_list(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    list_text, kb = await _game_list_kb(_TEST_SEL)
    await q.message.edit_text(
        "🎮 <b>O'yin faylini test qilish</b>\n\n"
        "Qaysi o'yinni tekshirmoqchisiz?\n\n" + list_text,
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith(_TEST_SEL))
async def cb_test_file_select(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    slug  = q.data[len(_TEST_SEL):]
    games = await get_all_games(only_active=False)
    game  = next((g for g in games if g["slug"] == slug), None)
    if not game:
        await q.answer("O'yin topilmadi.", show_alert=True)
        return
    code = _load_game_code(game["html_file"])
    if code is None:
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer("⏳ Tekshirilmoqda…")
    await q.message.edit_text(
        f"⏳ <b>{game['name']}</b> tekshirilmoqda…", parse_mode="HTML"
    )
    result = await services.ai_validate_code(code)
    header = (
        f"🧪 <b>{game['name']} — Test natijasi</b>\n"
        f"Fayl: <code>{game['html_file']}</code> ({_fmt_size(len(code.encode()))})\n\n"
    )
    if result.ok:
        body = header + result.content
        if len(body) <= _TG_MAX:
            await q.message.edit_text(body, reply_markup=_test_center_kb(), parse_mode="HTML")
        else:
            await q.message.edit_text(
                (header + result.content)[:_TG_MAX],
                reply_markup=_test_center_kb(),
                parse_mode="HTML",
            )
        await log_action(q.from_user.id, "AI_TEST_FILE", game["html_file"], "ok")
    else:
        await q.message.edit_text(
            f"❌ <b>Test xatosi</b>\n\n<code>{_esc(result.error or 'Noma`lum xato')}</code>",
            reply_markup=_test_center_kb(),
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Universal cancel for all Phase 5 FSM states
# ══════════════════════════════════════════════════════════════════════════════

_ALL_P5_STATES = StateFilter(
    AIBuilderStates.waiting_description,
    AIBuilderStates.pending_save,
    AIBuilderStates.waiting_filename,
    AIGameplayStates.waiting_change,
    AIGameplayStates.confirm_save,
    AIDesignStates.waiting_change,
    AIDesignStates.confirm_save,
    AIAssetStates.waiting_description,
    AIAssetStates.pending_save,
    AIAssetStates.waiting_filename,
    AICodeSaveStates.waiting_code,
    AICodeSaveStates.waiting_filename,
    AITestStates.waiting_code,
    AIAssetManagerFSM.pending_delete,
    AIAssetManagerFSM.waiting_upload,
)


@router.callback_query(_ALL_P5_STATES, lambda c: c.data == AI_CANCEL)
async def cb_p5_cancel(q: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(q.from_user.id):
        await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return
    await state.clear()
    await q.answer("Bekor qilindi.")
    await q.message.edit_text(
        AI_MENU_TEXT, reply_markup=ai_menu_keyboard(), parse_mode="HTML"
    )


@router.message(Command("cancel"), _ALL_P5_STATES)
async def cmd_p5_cancel(m: Message, state: FSMContext) -> None:
    if not _is_admin(m.from_user.id):
        return
    await state.clear()
    await m.answer(
        "✅ Bekor qilindi. /developer orqali menyuga qaytishingiz mumkin."
    )
