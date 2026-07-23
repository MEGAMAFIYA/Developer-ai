"""AI Developer — FSM handlers for the 8 live AI features.

Architecture
────────────
• This file is intentionally separate from handlers.py so the existing
  "coming soon" stubs are never touched.
• All AI calls go through services.py → manager → provider.
• No provider is imported or instantiated here.
• Every handler follows the same 4-step pattern:
    1. Guard (admin only)
    2. Set FSM state + show instructions
    3. Receive user input (message)
    4. Call service helper → format → reply

Multi-step flows
────────────────
✏️ Kodni tahrirlash needs two messages:
    step 1: receive original code  → AIEditCodeStates.waiting_code
    step 2: receive instruction    → AIEditCodeStates.waiting_instruction

All other flows are single-step.

Telegram message length
───────────────────────
Max 4096 chars per message.  Long AI responses are split with _send_long().

Cancel
──────
Every "waiting for input" keyboard has a ❌ Bekor qilish button (AI_CANCEL).
/cancel command is also accepted anywhere an FSM state is active.
Both clear state and restore the AI sub-menu.
"""

from __future__ import annotations

import logging
import re

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from handlers.developer.modules.ai import project_search as _ps
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL,
    AI_CHAT,
    AI_WRITE_CODE,
    AI_EDIT_CODE,
    AI_ANALYZE_CODE,
    AI_CREATE_GAME,
    AI_IMPROVE_GAME,
    AI_FIND_BUG,
    AI_FIX_BUG,
    AI_MENU,
)
from handlers.developer.modules.ai.menu import ai_menu_keyboard, AI_MENU_TEXT
from handlers.developer.modules.ai.states import (
    AIChatStates,
    AIWriteCodeStates,
    AIEditCodeStates,
    AIAnalyzeCodeStates,
    AICreateGameStates,
    AIImproveGameStates,
    AIFindBugStates,
    AIFixBugStates,
)
from handlers.developer.modules.ai import services
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:chat")

# ── Telegram limits ───────────────────────────────────────────────────────────
_TG_MAX = 4096

# ── All FSM states in this file (for the /cancel filter) ─────────────────────
_ALL_CHAT_STATES = StateFilter(
    AIChatStates.waiting_message,
    AIWriteCodeStates.waiting_prompt,
    AIEditCodeStates.waiting_code,
    AIEditCodeStates.waiting_instruction,
    AIAnalyzeCodeStates.waiting_code,
    AICreateGameStates.waiting_description,
    AIImproveGameStates.waiting_code,
    AIFindBugStates.waiting_code,
    AIFixBugStates.waiting_code,
)


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _cancel_kb() -> InlineKeyboardMarkup:
    """Shown while bot is waiting for user input."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=AI_CANCEL),
    ]])


def _result_kb() -> InlineKeyboardMarkup:
    """Shown after AI returns a result (single-turn features)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


def _chat_result_kb() -> InlineKeyboardMarkup:
    """Shown after each AI Chat reply — lets the user keep the conversation going."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=AI_CANCEL),
    ]])


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


async def _guard_cb(query: CallbackQuery) -> bool:
    if _is_admin(query.from_user.id):
        return True
    await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


async def _guard_msg(message: Message) -> bool:
    if _is_admin(message.from_user.id):
        return True
    await message.answer("⛔ Ruxsat yo'q.")
    return False


# ── Project command patterns ──────────────────────────────────────────────────
# Recognised in AI Chat before falling through to the normal AI provider.
# All patterns are case-insensitive.
#
# DISPATCH ORDER (matters — more specific patterns come first):
#   1. _RE_STRUCTURE   — whole-project tree, no folder argument
#   2. _RE_TREE_SUB    — subtree of a specific folder
#   3. _RE_LIST_FOLDER — "show/list [all] files in/inside <folder>"
#   4. _RE_LIST_PLAIN  — "list [all] <folder>"  (no "files" keyword required)
#   5. _RE_LIST_EVERY  — "list every/show all <folder>"
#   6. _RE_LIST_REVERSED — "<folder> files"
#   7. _RE_OPEN        — file opener (AFTER all list patterns to avoid grabbing them)
#   8. _RE_FIND        — identifier finder
#   9. _RE_SEARCH      — full-text grep

# ── Whole-project structure (no folder argument) ──────────────────────────────
_RE_STRUCTURE = re.compile(
    r"^\s*(?:project\s+structure|file\s+tree|project\s+map|list\s+all\s+files"
    r"|loyiha\s+tuzilmasi|fayl\s+xaritasi|analyze\s+project\s+structure)\s*$",
    re.IGNORECASE,
)

# ── Subtree: "tree handlers", "project tree handlers/developer", etc. ─────────
# Matches:  [project] (tree|structure|tuzilma) <folder>
# Does NOT match "project structure" alone (no folder) — that hits _RE_STRUCTURE.
_RE_TREE_SUB = re.compile(
    r"^\s*(?:project\s+)?(?:tree|structure|tuzilma)\s+(\S+(?:\/\S+)*)\s*$",
    re.IGNORECASE,
)

# ── Folder listing: "show/list [all] files in/inside <folder>" ───────────────
# Also: "files in/inside <folder>"
_RE_LIST_FOLDER = re.compile(
    r"""^\s*
        (?:
            (?:show|list)\s+(?:all\s+)?files?\s+(?:in|inside|under|from)\s+  |
            files?\s+(?:in|inside|under|from)\s+
        )
        (.+)$""",
    re.IGNORECASE | re.VERBOSE,
)

# ── Folder listing: "list [all] <folder>" or "show all <folder>" ──────────────
# Examples: "list handlers", "list all handlers/developer", "show all handlers"
# "show all X" is captured here (before _RE_LIST_EVERY) so the lazy quantifier
# in _RE_LIST_EVERY cannot strip a trailing 's' off the folder name.
# Plain "show X" (without "all") is intentionally excluded — it falls through
# to _RE_OPEN so bare filenames like "show main.py" still work correctly.
_RE_LIST_PLAIN = re.compile(
    r"^\s*(?:list\s+(?:all\s+)?|show\s+all\s+)(\S+(?:\/\S+)*)\s*$",
    re.IGNORECASE,
)

# ── Folder listing: "list every/show all <folder>" ───────────────────────────
_RE_LIST_EVERY = re.compile(
    r"^\s*(?:list\s+every|list\s+all|show\s+all)\s+(.+?)(?:\s+(?:module|file|fayl|handler|router))?s?\s*$",
    re.IGNORECASE,
)

# ── Folder listing: "<folder> files"  (folder name first) ────────────────────
# Example: "handlers files", "handlers/developer files"
_RE_LIST_REVERSED = re.compile(
    r"^\s*(\S+(?:\/\S+)*)\s+files?\s*$",
    re.IGNORECASE,
)

# ── File opener: "open/show/read <path>" ─────────────────────────────────────
# Intentionally last among the "show" patterns so list variants take priority.
_RE_OPEN = re.compile(
    r"^\s*(?:open|show|read|ko[`']?rsat|och(?:ir)?)\s+(.+)$",
    re.IGNORECASE,
)

# ── Identifier finder ─────────────────────────────────────────────────────────
_RE_FIND = re.compile(
    r"^\s*(?:find|locate|top(?:ish)?|izla)\s+(\S+)\s*$",
    re.IGNORECASE,
)

# ── Full-text search ──────────────────────────────────────────────────────────
_RE_SEARCH = re.compile(
    r"^\s*(?:search\s+for|search|grep|qidir(?:ish)?)\s+(.+)$",
    re.IGNORECASE,
)


async def _handle_project_command(text: str) -> "_ps.ProjectResult | None":
    """Detect and dispatch a project-aware command.

    Returns a ProjectResult if the text matches a known pattern,
    or None if it should be forwarded to the normal AI provider.

    Patterns are checked in priority order (most specific first) so that
    "show all files inside handlers" is never mis-parsed as open_file.
    """
    t = text.strip()

    # 1. Whole-project structure (exact phrases, no trailing folder)
    if _RE_STRUCTURE.match(t):
        return await _ps.project_structure()

    # 2. Subtree tree view: "tree handlers", "project structure handlers/dev"
    m = _RE_TREE_SUB.match(t)
    if m:
        return await _ps.list_files(m.group(1).strip())

    # 3. "show/list [all] files in/inside <folder>" or "files in <folder>"
    m = _RE_LIST_FOLDER.match(t)
    if m:
        return await _ps.list_files(m.group(1).strip())

    # 4. "list [all] <folder>"  (no "files" keyword required)
    m = _RE_LIST_PLAIN.match(t)
    if m:
        return await _ps.list_files(m.group(1).strip())

    # 5. "list every/show all <folder>"
    m = _RE_LIST_EVERY.match(t)
    if m:
        return await _ps.list_files(m.group(1).strip())

    # 6. "<folder> files"
    m = _RE_LIST_REVERSED.match(t)
    if m:
        return await _ps.list_files(m.group(1).strip())

    # 7. File opener — checked AFTER all list patterns
    m = _RE_OPEN.match(t)
    if m:
        return await _ps.open_file(m.group(1).strip())

    # 8. Identifier finder
    m = _RE_FIND.match(t)
    if m:
        return await _ps.find_identifier(m.group(1).strip())

    # 9. Full-text search
    m = _RE_SEARCH.match(t)
    if m:
        return await _ps.search_text(m.group(1).strip())

    return None


async def _send_project_result(message: Message, result: "_ps.ProjectResult") -> None:
    """Send a ProjectResult back to the user inside an AI Chat session.

    Keeps FSM state active (no clear) so the conversation continues.
    Uses _chat_result_kb() so the ❌ Bekor qilish button is always present.
    Falls back from HTML to plain text on TelegramBadRequest.
    """
    text = result.text
    if len(text) <= _TG_MAX:
        try:
            await message.answer(text, reply_markup=_chat_result_kb(), parse_mode="HTML")
        except TelegramBadRequest:
            await message.answer(text, reply_markup=_chat_result_kb())
        return
    # Long result — split into chunks; last chunk gets the keyboard
    chunks = [text[i: i + _TG_MAX] for i in range(0, len(text), _TG_MAX)]
    for idx, chunk in enumerate(chunks):
        kb = _chat_result_kb() if idx == len(chunks) - 1 else None
        try:
            await message.answer(chunk, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            await message.answer(chunk, reply_markup=kb)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send_long(message: Message, text: str) -> None:
    """Send text, splitting into ≤4096-char chunks if needed.

    The last chunk gets the "back to menu" button; intermediate chunks have none.
    Each chunk falls back to plain text if HTML parse fails.
    """
    for i in range(0, len(text), _TG_MAX):
        chunk = text[i: i + _TG_MAX]
        kb = _result_kb() if i + _TG_MAX >= len(text) else None
        try:
            await message.answer(
                chunk,
                reply_markup=kb,
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            await message.answer(
                chunk,
                reply_markup=kb,
            )


async def _process(
    message: Message,
    state: FSMContext,
    feature_name: str,
    coro,
    action: str = "AI_FEATURE",
) -> None:
    """Generic single-turn handler: clears FSM, awaits AI, shows result.

    *action* is the log key written to ai_actions.log, e.g. ``"AI_WRITE_CODE"``.
    Successful calls log ``action`` with result ``"ok"``; failures log
    ``action + "_ERROR"`` with the error message.
    """
    await state.clear()
    sent = await message.answer(
        f"⏳ <b>{feature_name}</b> — AI javob tayyorlamoqda…",
        parse_mode="HTML",
    )
    result = await coro
    if result.ok:
        text = result.content
        if len(text) <= _TG_MAX:
            try:
                await sent.edit_text(
                    text,
                    reply_markup=_result_kb(),
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                await sent.edit_text(
                    text,
                    reply_markup=_result_kb(),
                    parse_mode=None,
                )
        else:
            await sent.delete()
            await _send_long(message, text)
        await log_action(message.from_user.id, action, feature_name, "ok")
    else:
        err_msg = result.error or "Noma\u02bblum xato"
        await sent.edit_text(
            f"❌ <b>Xato</b>\n\n<code>{err_msg}</code>",
            reply_markup=_result_kb(),
            parse_mode="HTML",
        )
        await log_action(
            message.from_user.id,
            f"{action}_ERROR",
            feature_name,
            err_msg[:200],
        )


async def _chat_process(message: Message, coro) -> None:
    """AI Chat handler — does NOT clear FSM state so the conversation continues.

    After each reply the ❌ Bekor qilish button is shown; the user can keep
    sending messages until they explicitly cancel.

    Logs one ``AI_CHAT`` entry per completed turn (success or error).
    """
    sent = await message.answer(
        "⏳ <b>AI Chat</b> — javob tayyorlamoqda…",
        parse_mode="HTML",
    )

    result = await coro
    prompt = (message.text or "")[:100]   # first 100 chars as context for the log

    if result.ok:
        text = result.content

        if not text.strip():
            await sent.edit_text(
                "⚠️ AI bo'sh javob qaytardi. Iltimos, boshqacha so'rang.",
                reply_markup=_chat_result_kb(),
                parse_mode="HTML",
            )
            await log_action(
                message.from_user.id, "AI_CHAT_ERROR", prompt, "empty_response"
            )
            return

        if len(text) <= _TG_MAX:
            try:
                await sent.edit_text(
                    text,
                    reply_markup=_chat_result_kb(),
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                await sent.edit_text(
                    text,
                    reply_markup=_chat_result_kb(),
                    parse_mode=None,
                )
        else:
            await sent.delete()
            # Send all chunks; attach cancel button only to the last one
            chunks = [text[i: i + _TG_MAX] for i in range(0, len(text), _TG_MAX)]
            for idx, chunk in enumerate(chunks):
                kb = _chat_result_kb() if idx == len(chunks) - 1 else None
                try:
                    await message.answer(
                        chunk,
                        reply_markup=kb,
                        parse_mode="HTML",
                    )
                except TelegramBadRequest:
                    await message.answer(
                        chunk,
                        reply_markup=kb,
                    )
        await log_action(message.from_user.id, "AI_CHAT", prompt, "ok")
    else:
        err_msg = result.error or "Noma\u02bblum xato"
        try:
            await sent.edit_text(
                f"❌ <b>Xato</b>\n\n<code>{err_msg}</code>",
                reply_markup=_chat_result_kb(),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            await sent.edit_text(
                f"❌ Xato\n\n{err_msg}",
                reply_markup=_chat_result_kb(),
            )
        await log_action(
            message.from_user.id, "AI_CHAT_ERROR", prompt, err_msg[:200]
        )


# ── ❌ Cancel (callback + /cancel command) ────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_CANCEL)
async def cb_cancel(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await query.answer("Bekor qilindi.")
    await query.message.edit_text(
        AI_MENU_TEXT,
        reply_markup=ai_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("cancel"), _ALL_CHAT_STATES)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    await state.clear()
    await message.answer(
        "✅ Bekor qilindi. /developer orqali menyuga qaytishingiz mumkin."
    )


# ── 💬 AI Chat ────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_CHAT)
async def cb_chat_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIChatStates.waiting_message)
    await query.answer()
    await query.message.edit_text(
        "💬 <b>AI Chat</b>\n\n"
        "Savolingizni yoki muammoingizni yozing.\n"
        "AI o'zbek tilida javob beradi.\n\n"
        "<i>Misol: «Snake o'yinida tezlikni qanday oshiraman?»</i>\n\n"
        "📁 <b>Loyiha buyruqlari:</b>\n"
        "<code>Open services.py</code>\n"
        "<code>Find _chat_process</code>\n"
        "<code>Search for TelegramBadRequest</code>\n"
        "<code>Show all files inside handlers</code>\n"
        "<code>List every ai module</code>\n"
        "<code>Project structure</code>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIChatStates.waiting_message)
async def msg_chat(message: Message, state: FSMContext) -> None:
    """Receive user message and reply — FSM state stays active for next message.

    Project-aware commands (open/find/search/list) are handled locally before
    the message is forwarded to the AI provider.  FSM state is never cleared
    here; it is cleared only when the user presses ❌ Bekor qilish.
    """
    if not await _guard_msg(message):
        return
    user_text = message.text or ""

    # ── Try project command first ──────────────────────────────────────────
    project_result = await _handle_project_command(user_text)
    if project_result is not None:
        await _send_project_result(message, project_result)
        return

    # ── Normal AI chat ─────────────────────────────────────────────────────
    await _chat_process(message, services.ai_chat(user_text))


# ── 📝 Kod yozdirish ──────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_WRITE_CODE)
async def cb_write_code_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIWriteCodeStates.waiting_prompt)
    await query.answer()
    await query.message.edit_text(
        "📝 <b>Kod yozdirish</b>\n\n"
        "Qanday kod kerakligini yozing.\n"
        "Til ko'rsatmasangiz, JavaScript ishlatiladi.\n\n"
        "<i>Misol: «Canvas da 5 ta yulduz animatsiyasini chiz»</i>\n"
        "<i>Misol: «Oyinchi tezligi 200 dan 300 ga oshiradigan funksiya»</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIWriteCodeStates.waiting_prompt)
async def msg_write_code(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    text = message.text or ""
    # Detect language hint from user message
    lang = "javascript"
    lower = text.lower()
    if "html" in lower:
        lang = "html"
    elif "css" in lower:
        lang = "css"
    elif "python" in lower:
        lang = "python"
    await _process(
        message, state,
        "Kod yozdirish",
        services.ai_write_code(text, language=lang),
        "AI_WRITE_CODE",
    )


# ── ✏️ Kodni tahrirlash (2-step) ──────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_EDIT_CODE)
async def cb_edit_code_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIEditCodeStates.waiting_code)
    await query.answer()
    await query.message.edit_text(
        "✏️ <b>Kodni tahrirlash — 1/2</b>\n\n"
        "Tahrirlash kerak bo'lgan kodni yuboring.\n\n"
        "<i>Butun fayl yoki kerakli qism bo'lishi mumkin.</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIEditCodeStates.waiting_code)
async def msg_edit_code_receive(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    code = message.text or ""
    if not code.strip():
        await message.answer("⚠️ Kod bo'sh. Iltimos kodni yuboring.")
        return
    await state.update_data(code=code)
    await state.set_state(AIEditCodeStates.waiting_instruction)
    await message.answer(
        "✏️ <b>Kodni tahrirlash — 2/2</b>\n\n"
        "Nima o'zgartirish kerakligini yozing.\n\n"
        "<i>Misol: «Tezlikni 2 barobarga oshir»</i>\n"
        "<i>Misol: «Chap tomondagi panelni olib tashla»</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIEditCodeStates.waiting_instruction)
async def msg_edit_code_instruct(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    data = await state.get_data()
    code = data.get("code", "")
    instruction = message.text or ""
    await _process(
        message, state,
        "Kodni tahrirlash",
        services.ai_edit_code(code, instruction),
        "AI_EDIT_CODE",
    )


# ── 🔍 Kodni tahlil qilish ────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_ANALYZE_CODE)
async def cb_analyze_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIAnalyzeCodeStates.waiting_code)
    await query.answer()
    await query.message.edit_text(
        "🔍 <b>Kodni tahlil qilish</b>\n\n"
        "Tahlil qilinadigan kodni yuboring.\n\n"
        "AI quyidagi yo'nalishlarda tekshiradi:\n"
        "• 🐛 Xatolar va muammolar\n"
        "• ⚡ Samaradorlik\n"
        "• 🔒 Xavfsizlik",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIAnalyzeCodeStates.waiting_code)
async def msg_analyze(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    await _process(
        message, state,
        "Kodni tahlil qilish",
        services.ai_analyze_code(message.text or ""),
        "AI_ANALYZE_CODE",
    )


# ── 🎮 O'yin yaratish ─────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_CREATE_GAME)
async def cb_create_game_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AICreateGameStates.waiting_description)
    await query.answer()
    await query.message.edit_text(
        "🎮 <b>O'yin yaratish</b>\n\n"
        "O'yin g'oyasini batafsil tasvirlab bering.\n"
        "AI HTML5 canvas o'yinini bitta faylda yaratib beradi.\n\n"
        "<i>Misol: «Kosmosda uchayotgan kemani boshqaramiz, "
        "meteoritlardan qochamiz, o'q otamiz»</i>\n\n"
        "⏱ Yaratish 30–60 soniya olishi mumkin.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AICreateGameStates.waiting_description)
async def msg_create_game(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    await _process(
        message, state,
        "O'yin yaratish",
        services.ai_create_game(message.text or ""),
        "AI_CREATE_GAME",
    )


# ── 🛠 O'yinni yaxshilash ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_IMPROVE_GAME)
async def cb_improve_game_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIImproveGameStates.waiting_code)
    await query.answer()
    await query.message.edit_text(
        "🛠 <b>O'yinni yaxshilash</b>\n\n"
        "O'yin kodini yuboring.\n"
        "AI samaradorlik, UX va kod sifatini yaxshilab qaytaradi.\n\n"
        "<i>Butun HTML faylni yuboring — AI hammasini tahlil qiladi.</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIImproveGameStates.waiting_code)
async def msg_improve_game(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    await _process(
        message, state,
        "O'yinni yaxshilash",
        services.ai_improve_game(message.text or ""),
        "AI_IMPROVE_GAME",
    )


# ── 🧠 Bug topish ──────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_FIND_BUG)
async def cb_find_bug_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIFindBugStates.waiting_code)
    await query.answer()
    await query.message.edit_text(
        "🧠 <b>Bug topish</b>\n\n"
        "Tekshirilishi kerak bo'lgan kodni yuboring.\n"
        "AI barcha potensial muammolarni topib, "
        "qaysi qatorda va qanday tuzatish kerakligini bildiradi.",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIFindBugStates.waiting_code)
async def msg_find_bug(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    await _process(
        message, state,
        "Bug topish",
        services.ai_find_bugs(message.text or ""),
        "AI_FIND_BUG",
    )


# ── ❌ Xatoni tuzatish ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_FIX_BUG)
async def cb_fix_bug_start(query: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(query):
        return
    await state.clear()
    await state.set_state(AIFixBugStates.waiting_code)
    await query.answer()
    await query.message.edit_text(
        "❌ <b>Xatoni tuzatish</b>\n\n"
        "Xatoli kodni yuboring.\n"
        "AI barcha xatolarni tuzatib, "
        "tuzatilgan to'liq kodni qaytaradi.\n\n"
        "<i>O'zgartirilgan joylar <code>// FIX:</code> izoh bilan belgilanadi.</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AIFixBugStates.waiting_code)
async def msg_fix_bug(message: Message, state: FSMContext) -> None:
    if not await _guard_msg(message):
        return
    await _process(
        message, state,
        "Xatoni tuzatish",
        services.ai_fix_bug(message.text or ""),
        "AI_FIX_BUG",
    )
