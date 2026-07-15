"""Developer Mode › 🌐 GitHub Manager

Features
────────
📋 So'nggi commitlar — GitHub API orqali (token talab qilinadi)
📊 Repo holati       — branch, oxirgi commit, ochiq PR soni
🔄 Git Pull          — joriy repozitoriyani yangilash (tasdiq kerak)
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config as cfg
from handlers.developer.callbacks import (
    DEV_GITHUB,
    DEV_GH_COMMITS,
    DEV_GH_PULL,
    DEV_GH_PULL_OK,
    DEV_GH_STATUS,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:github")

_TG_MAX  = 4096
_REPO_DIR = Path(__file__).resolve().parents[4]   # project root (above gamehub/)


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _gh_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Commitlar",    callback_data=DEV_GH_COMMITS),
            InlineKeyboardButton(text="📊 Holat",        callback_data=DEV_GH_STATUS),
        ],
        [
            InlineKeyboardButton(text="🔄 Git Pull",     callback_data=DEV_GH_PULL),
            InlineKeyboardButton(text="⬅️ Orqaga",       callback_data="dev:menu"),
        ],
    ])


def _confirm_pull_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, pull",   callback_data=DEV_GH_PULL_OK),
        InlineKeyboardButton(text="❌ Bekor",       callback_data=DEV_GITHUB),
    ]])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _git_run(*args: str, cwd: Path = _REPO_DIR) -> tuple[int, str, str]:
    """Run a git command asynchronously, return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    except asyncio.TimeoutError:
        return -1, "", "Timeout: 30 soniya ichida javob kelmadi"
    except FileNotFoundError:
        return -1, "", "git topilmadi"
    except Exception as exc:
        return -1, "", str(exc)


async def _git_log(n: int = 10) -> str:
    rc, out, err = await _git_run(
        "log", f"-{n}",
        "--pretty=format:%h|%an|%ar|%s",
        "--no-merges",
    )
    if rc != 0:
        if not cfg.config.GITHUB_OWNER:
            return (
                "⚠️ GitHub konfiguratsiya qilinmagan.\n\n"
                "GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH ni .env ga qo'shing."
            )
        return f"❌ git log xato: {err or 'noma`lum'}"
    if not out.strip():
        return "Hech qanday commit topilmadi."
    lines = ["📋 <b>So'nggi commitlar</b>\n"]
    for line in out.strip().split("\n"):
        parts = line.split("|", 3)
        if len(parts) == 4:
            sha, author, when, msg = parts
            lines.append(f"<code>{sha}</code> <b>{msg[:60]}</b>\n   {author} • {when}")
        else:
            lines.append(line)
    return "\n\n".join(lines)


async def _git_status() -> str:
    lines = ["📊 <b>Repo holati</b>\n"]

    # Branch
    rc, out, _ = await _git_run("rev-parse", "--abbrev-ref", "HEAD")
    branch = out.strip() if rc == 0 else "?"
    lines.append(f"🌿 Branch: <code>{branch}</code>")

    # Last commit
    rc, out, _ = await _git_run("log", "-1", "--pretty=format:%h %s (%ar)")
    if rc == 0 and out.strip():
        lines.append(f"📌 Oxirgi: <code>{out.strip()[:80]}</code>")

    # Uncommitted changes
    rc, out, _ = await _git_run("status", "--porcelain")
    if rc == 0:
        changed = [l for l in out.strip().split("\n") if l.strip()]
        if changed:
            lines.append(f"⚠️ O'zgartirilgan fayllar: {len(changed)} ta")
        else:
            lines.append("✅ Ish daraxtida o'zgarishlar yo'q")

    # Remote URL
    rc, out, _ = await _git_run("remote", "get-url", "origin")
    if rc == 0 and out.strip():
        url = out.strip()
        # mask token if embedded in URL
        if "@" in url:
            url = "https://github.com/***"
        lines.append(f"🔗 Remote: <code>{url}</code>")

    return "\n".join(lines)


async def _git_pull() -> str:
    rc, out, err = await _git_run("pull", "--ff-only")
    combined = (out + err).strip()
    if rc == 0:
        return f"✅ Pull muvaffaqiyatli:\n<code>{combined[:500]}</code>"
    return f"❌ Pull xatosi (kod {rc}):\n<code>{combined[:500]}</code>"


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_GITHUB)
async def cb_github_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    configured = bool(cfg.config.GITHUB_OWNER and cfg.config.GITHUB_REPO)
    note = (
        f"Repo: <code>{cfg.config.GITHUB_OWNER}/{cfg.config.GITHUB_REPO}</code> "
        f"[{cfg.config.GITHUB_BRANCH}]"
        if configured else
        "⚠️ GITHUB_OWNER / GITHUB_REPO sozlanmagan — git buyruqlari lokal git orqali ishlaydi."
    )
    await q.message.edit_text(
        f"🌐 <b>GitHub Manager</b>\n\n{note}",
        reply_markup=_gh_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_GH_COMMITS)
async def cb_gh_commits(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Yuklanmoqda…")
    text = await _git_log(10)
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_GH_STATUS)
async def cb_gh_status(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _git_status()
    await q.message.edit_text(
        text[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == DEV_GH_PULL)
async def cb_gh_pull_confirm(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🔄 <b>Git Pull</b>\n\n"
        "Joriy branch oxirgi o'zgarishlar bilan yangilanadi.\n"
        "Bu faqat fast-forward pull (--ff-only).\n\n"
        "⚠️ Davom etasizmi?",
        reply_markup=_confirm_pull_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_GH_PULL_OK)
async def cb_gh_pull_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Pull bajarilmoqda…")
    result = await _git_pull()
    await log_action(q.from_user.id, "GIT_PULL", str(_REPO_DIR.name), result[:100])
    await q.message.edit_text(
        result[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML"
    )
