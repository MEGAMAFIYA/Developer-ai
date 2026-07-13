"""AI Developer Phase 4 — GitHub Tools.

Features
────────
🌐 GitHub Clone   — clone a repo into gamehub/clones/ (preview → confirm → run)
📤 GitHub Commit  — git add -A + commit with message (preview → confirm → run)
🚀 GitHub Push    — push current branch (preview → confirm → run)
📥 GitHub Pull    — pull current branch (preview → confirm → run)

All operations show a preview screen before executing.
Uses asyncio subprocess so the bot loop is never blocked.
Git binary must be available in PATH (standard in Replit).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

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
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL, AI_MENU,
    AI_GH_CLONE, AI_GH_COMMIT, AI_GH_PUSH, AI_GH_PULL,
    AI_GH_OK,
)
from handlers.developer.modules.ai.menu import ai_menu_keyboard, AI_MENU_TEXT
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:github_tools")

_BASE      = Path(__file__).resolve().parents[4]   # gamehub/
_CLONE_DIR = _BASE / "clones"
_GIT_ROOT  = _BASE.parent                          # workspace/ (project root)
_TG_MAX    = 4096


# ── FSM States ────────────────────────────────────────────────────────────────

class GHStates(StatesGroup):
    """Single state group for all GitHub operations.

    'operation' key in FSM data carries: clone | commit | push | pull
    'input'     key carries: clone URL or commit message
    """
    waiting_input = State()   # clone: URL, commit: message
    confirming    = State()   # push & pull also use this directly


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

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])

def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash", callback_data=AI_GH_OK),
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="AI Menyuga qaytish", callback_data=AI_MENU),
    ]])


# ── Git helpers ───────────────────────────────────────────────────────────────

async def _git(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a git command; returns (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd or _GIT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def _git_current_branch() -> str:
    rc, out, _ = await _git("branch", "--show-current")
    return out.strip() if rc == 0 else "unknown"


async def _git_status() -> str:
    rc, out, err = await _git("status", "--short")
    if rc != 0:
        return err.strip() or "git status xatosi"
    return out.strip() or "Hech qanday o'zgarish yo'q (working tree clean)"


async def _git_log_short(n: int = 5) -> str:
    rc, out, _ = await _git("log", f"--oneline", f"-{n}")
    return out.strip() if rc == 0 else "log mavjud emas"


# ════════════════════════════════════════════════════════════════════════════
# 🌐 GitHub Clone
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_GH_CLONE)
async def cb_gh_clone_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.update_data(operation="clone")
    await state.set_state(GHStates.waiting_input)
    await q.answer()
    await q.message.edit_text(
        "<b>GitHub Clone</b>\n\n"
        "Repo URL yozing:\n\n"
        "<code>https://github.com/owner/repo.git</code>\n\n"
        "Klonlash gamehub/clones/ papkasiga amalga oshiriladi.",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


@router.message(GHStates.waiting_input)
async def msg_gh_waiting_input(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    data = await state.get_data()
    op   = data.get("operation", "")
    inp  = m.text or ""

    if op == "clone":
        url      = inp.strip()
        repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest      = _CLONE_DIR / repo_name
        await state.update_data(input=url)
        await state.set_state(GHStates.confirming)
        await m.answer(
            f"<b>Clone — preview</b>\n\n"
            f"URL: <code>{url}</code>\n"
            f"Papka: <code>clones/{repo_name}</code>\n"
            f"Mavjud: {'HA (qayta klon)' if dest.exists() else 'YO'Q'}\n\n"
            "Tasdiqlaysizmi?",
            reply_markup=_confirm_kb(), parse_mode="HTML",
        )

    elif op == "commit":
        msg_text  = inp.strip()
        status    = await _git_status()
        branch    = await _git_current_branch()
        await state.update_data(input=msg_text)
        await state.set_state(GHStates.confirming)
        await m.answer(
            f"<b>Commit — preview</b>\n\n"
            f"Branch: <code>{branch}</code>\n"
            f"Xabar: <code>{msg_text}</code>\n\n"
            f"O'zgarishlar:\n<pre>{status[:600]}</pre>\n\n"
            "Tasdiqlaysizmi?",
            reply_markup=_confirm_kb(), parse_mode="HTML",
        )


# ════════════════════════════════════════════════════════════════════════════
# 📤 GitHub Commit
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_GH_COMMIT)
async def cb_gh_commit_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.update_data(operation="commit")
    await state.set_state(GHStates.waiting_input)
    await q.answer()
    status = await _git_status()
    await q.message.edit_text(
        "<b>GitHub Commit</b>\n\n"
        f"Joriy holat:\n<pre>{status[:500]}</pre>\n\n"
        "Commit xabarini yozing:",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════════════════════════
# 🚀 GitHub Push
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_GH_PUSH)
async def cb_gh_push_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.update_data(operation="push")
    await state.set_state(GHStates.confirming)
    await q.answer()
    branch  = await _git_current_branch()
    recent  = await _git_log_short(3)
    await q.message.edit_text(
        f"<b>GitHub Push — preview</b>\n\n"
        f"Branch: <code>{branch}</code>\n\n"
        f"So'nggi commitlar:\n<pre>{recent[:500]}</pre>\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(), parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════════════════════════
# 📥 GitHub Pull
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_GH_PULL)
async def cb_gh_pull_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.update_data(operation="pull")
    await state.set_state(GHStates.confirming)
    await q.answer()
    branch = await _git_current_branch()
    await q.message.edit_text(
        f"<b>GitHub Pull — preview</b>\n\n"
        f"Branch: <code>{branch}</code>\n"
        f"Manba: origin/{branch}\n\n"
        "Mahalliy o'zgarishlar mavjud bo'lsa, konflikt yuzaga kelishi mumkin.\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(), parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════════════════════════
# ✅ Confirm dispatcher
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(
    lambda c: c.data == AI_GH_OK,
    StateFilter(GHStates.confirming),
)
async def cb_gh_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    op   = data.get("operation", "")
    inp  = data.get("input", "")
    await state.clear()
    await q.answer()

    sent = await q.message.edit_text(
        f"Bajarilmoqda: <b>{op}</b> ...",
        parse_mode="HTML",
    )

    try:
        if op == "clone":
            url  = inp
            name = url.rstrip("/").split("/")[-1].removesuffix(".git")
            dest = _CLONE_DIR / name
            _CLONE_DIR.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                import shutil
                await asyncio.to_thread(shutil.rmtree, str(dest))
            rc, out, err = await _git("clone", url, str(dest), cwd=_CLONE_DIR)
            result = out or err

        elif op == "commit":
            # Configure git user if not set
            await _git("config", "user.email", "bot@gamehub.local")
            await _git("config", "user.name", "GameHub Bot")
            rc_add, _, err_add = await _git("add", "-A")
            if rc_add != 0:
                rc, result = rc_add, err_add
            else:
                rc, out, err = await _git("commit", "-m", inp)
                result = out or err

        elif op == "push":
            branch       = await _git_current_branch()
            rc, out, err = await _git("push", "origin", branch)
            result       = out or err

        elif op == "pull":
            rc, out, err = await _git("pull")
            result       = out or err

        else:
            rc, result = 1, "Noma'lum amal"

        status_icon = "Bajarildi" if rc == 0 else "Xato"
        await sent.edit_text(
            f"<b>{op.upper()} — {status_icon}</b>\n\n"
            f"<pre>{result[:1500]}</pre>",
            reply_markup=_back_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, f"GH_{op.upper()}", inp[:100],
                         "ok" if rc == 0 else f"rc={rc}")
    except Exception as exc:
        await sent.edit_text(f"Xato: <code>{exc}</code>",
                             reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(q.from_user.id, f"GH_{op.upper()}", inp[:100], f"exc:{exc}")
