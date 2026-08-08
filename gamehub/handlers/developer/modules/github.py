"""Developer Mode GitHub Manager backed exclusively by the GitHub API."""

from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from handlers.developer.callbacks import (
    DEV_GITHUB, DEV_GH_COMMITS, DEV_GH_PULL, DEV_GH_PULL_OK, DEV_GH_STATUS,
)
from handlers.developer.modules.ai.action_log import log_action
from services.project_provider import ProjectProviderError, get_project_provider

logger = logging.getLogger(__name__)
router = Router(name="dev:github")
_TG_MAX = 4096


def _is_admin(uid: int) -> bool:
    return uid == config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


def _gh_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Commitlar", callback_data=DEV_GH_COMMITS),
            InlineKeyboardButton(text="📊 Holat", callback_data=DEV_GH_STATUS),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data=DEV_GH_PULL),
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="dev:menu"),
        ],
    ])


def _confirm_pull_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, yangila", callback_data=DEV_GH_PULL_OK),
        InlineKeyboardButton(text="❌ Bekor", callback_data=DEV_GITHUB),
    ]])


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


async def _error_text(exc: Exception) -> str:
    return f"❌ GitHub xatosi: <code>{_esc(str(exc))}</code>"


@router.callback_query(lambda c: c.data == DEV_GITHUB)
async def cb_github_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    try:
        label = await get_project_provider().repository_label()
        note = f"Repo: <code>{_esc(label)}</code>"
    except Exception as exc:
        note = await _error_text(exc)
    await q.message.edit_text(
        f"🌐 <b>GitHub Manager</b>\n\n{note}\n\n"
        "Barcha loyiha amallari GitHub API orqali bajariladi; local Git ishlatilmaydi.",
        reply_markup=_gh_keyboard(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_GH_COMMITS)
async def cb_gh_commits(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Yuklanmoqda…")
    try:
        commits = await get_project_provider().recent_commits(10)
        lines = ["📋 <b>So'nggi GitHub commitlar</b>\n"]
        for commit in commits:
            sha = str(commit.get("sha", ""))[:7]
            info = commit.get("commit", {}) or {}
            message = str(info.get("message", "")).splitlines()[0][:70]
            author = (info.get("author", {}) or {}).get("name", "unknown")
            date = (info.get("author", {}) or {}).get("date", "")
            lines.append(f"<code>{_esc(sha)}</code> <b>{_esc(message)}</b>\n   {_esc(str(author))} • {_esc(str(date))}")
        text = "\n\n".join(lines) if commits else "Hech qanday commit topilmadi."
    except Exception as exc:
        text = await _error_text(exc)
    await q.message.edit_text(text[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_GH_STATUS)
async def cb_gh_status(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    try:
        provider = get_project_provider()
        status = await provider.repository_status()
        entries = await provider.tree()
        files = sum(entry.kind == "file" for entry in entries)
        dirs = sum(entry.kind == "dir" for entry in entries)
        text = (
            "📊 <b>GitHub repository holati</b>\n\n"
            f"Repo: <code>{_esc(status['owner'])}/{_esc(status['repo'])}</code>\n"
            f"Branch: <code>{_esc(status['branch'])}</code>\n"
            f"Fayllar: <b>{files:,}</b> | Papkalar: <b>{dirs:,}</b>\n"
            f"Ochiq issues: <b>{status['open_issues']}</b>\n"
            f"Yangilangan: <code>{_esc(status['updated_at'])}</code>"
        )
    except Exception as exc:
        text = await _error_text(exc)
    await q.message.edit_text(text[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == DEV_GH_PULL)
async def cb_gh_pull_confirm(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "🔄 <b>GitHub ma'lumotlarini yangilash</b>\n\n"
        "Repository tree va fayl cache GitHub branch holatiga moslanadi.\n"
        "Render/local fayllar o'zgartirilmaydi.\n\nDavom etasizmi?",
        reply_markup=_confirm_pull_kb(), parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_GH_PULL_OK)
async def cb_gh_pull_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Yangilanmoqda…")
    try:
        entries = await get_project_provider().refresh()
        result = f"✅ GitHub cache yangilandi: {len(entries)} ta repository entry."
        outcome = "ok"
    except Exception as exc:
        result = await _error_text(exc)
        outcome = f"error:{exc}"
    await log_action(q.from_user.id, "GITHUB_REFRESH", "repository", outcome)
    await q.message.edit_text(result[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML")