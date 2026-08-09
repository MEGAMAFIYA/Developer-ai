"""Developer Mode GitHub Manager backed exclusively by the GitHub API."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from database.game_db import delete_scores_by_game_name
from database.global_db import (
    delete_game_by_slug,
    get_all_games,
    is_image_url_shared,
)
from handlers.developer.callbacks import (
    DEV_GITHUB, DEV_GH_COMMITS, DEV_GH_PULL, DEV_GH_PULL_OK, DEV_GH_STATUS,
)
from handlers.developer.modules.ai.action_log import log_action
from services.upload_service import WEBAPP_DIR
from services.project_provider import ProjectProviderError, get_project_provider

logger = logging.getLogger(__name__)
router = Router(name="dev:github")
_TG_MAX = 4096
_GAMES_DIR = "webapp/games"
_GAME_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")
_SYSTEM_GAME_STEMS = frozenset({
    "404",
    "500",
    "favicon",
    "health",
    "index",
    "manifest",
    "robots",
    "service-worker",
    "sw",
})


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
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=DEV_GH_PULL_OK),
        InlineKeyboardButton(text="❌ Bekor", callback_data=DEV_GITHUB),
    ]])


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


async def _error_text(exc: Exception) -> str:
    return f"❌ GitHub xatosi: <code>{_esc(str(exc))}</code>"


def _github_game_slugs(entries) -> set[str]:
    """Return only direct, valid HTML game slugs from webapp/games/."""
    slugs: set[str] = set()
    prefix = f"{_GAMES_DIR}/"
    for entry in entries:
        if entry.kind != "file" or not entry.path.startswith(prefix):
            continue
        filename = entry.path.removeprefix(prefix)
        if "/" in filename or not filename.lower().endswith(".html"):
            continue
        slug = filename[:-5]
        if (
            _GAME_SLUG_RE.fullmatch(slug)
            and slug.lower() not in _SYSTEM_GAME_STEMS
            and not slug.startswith(("_", "."))
        ):
            slugs.add(slug)
    return slugs


async def _server_games_missing_from_github() -> list[dict]:
    provider = get_project_provider()
    entries = await provider.refresh()
    github_slugs = _github_game_slugs(entries)
    server_games = await get_all_games(only_active=False)
    return sorted(
        (game for game in server_games if game["slug"] not in github_slugs),
        key=lambda game: game["slug"],
    )


def _unlink_if_inside(path: Path, root: Path) -> bool:
    """Remove a local file only when it is safely inside the expected root."""
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    if not resolved.is_file():
        return False
    resolved.unlink()
    return True


async def _delete_server_game(game: dict) -> dict:
    """Remove one GitHub-missing game from all server-side stores."""
    slug = str(game["slug"])
    html_file = str(game.get("html_file") or f"{slug}.html")
    html_path = WEBAPP_DIR / "games" / html_file
    html_deleted = _unlink_if_inside(html_path, WEBAPP_DIR / "games")

    deleted_rows = await delete_game_by_slug(slug)
    deleted_slugs = {str(row["slug"]) for row in deleted_rows}
    if not deleted_rows and slug not in deleted_slugs:
        # Keep the cleanup keyed to the registry slug if html_file is stale.
        deleted_slugs.add(slug)

    scores_deleted = 0
    for deleted_slug in deleted_slugs:
        scores_deleted += await delete_scores_by_game_name(deleted_slug)

    images_deleted = 0
    for row in deleted_rows:
        image_url = str(row.get("image_url") or "")
        if not image_url.startswith("/webapp/"):
            continue
        image_path = WEBAPP_DIR / image_url.removeprefix("/webapp/")
        if await is_image_url_shared(image_url):
            continue
        if _unlink_if_inside(image_path, WEBAPP_DIR):
            images_deleted += 1

    return {
        "slug": slug,
        "html_deleted": html_deleted,
        "db_deleted": len(deleted_rows),
        "scores_deleted": scores_deleted,
        "images_deleted": images_deleted,
    }


def _missing_games_text(games: list[dict]) -> str:
    lines = [
        "⚠️ <b>GitHub’da yo‘q, serverdan o‘chiriladigan o‘yinlar:</b>",
        "",
    ]
    lines.extend(
        f"• <code>{_esc(str(game['slug']))}</code> — {_esc(str(game.get('name') or ''))}"
        for game in games
    )
    lines.extend([
        "",
        "GitHub’da mavjud o‘yinlarga tegilmaydi.",
        "Tasdiqlangandan keyin server HTML, registry va reyting ma’lumotlari o‘chiriladi.",
    ])
    return "\n".join(lines)


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
    try:
        missing_games = await _server_games_missing_from_github()
    except Exception as exc:
        await q.message.edit_text(
            await _error_text(exc),
            reply_markup=_gh_keyboard(),
            parse_mode="HTML",
        )
        return

    if not missing_games:
        await q.message.edit_text(
            "✅ <b>GitHub ma'lumotlari yangilandi.</b>\n\n"
            "GitHub’da yo‘q server o‘yinlari topilmadi.\n"
            "GitHub’da mavjud o‘yinlarga tegilmadi.",
            reply_markup=_gh_keyboard(),
            parse_mode="HTML",
        )
        return

    await q.message.edit_text(
        _missing_games_text(missing_games)[:_TG_MAX],
        reply_markup=_confirm_pull_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_GH_PULL_OK)
async def cb_gh_pull_ok(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer("⏳ Yangilanmoqda…")
    try:
        missing_games = await _server_games_missing_from_github()
        deleted = [await _delete_server_game(game) for game in missing_games]
        await get_project_provider().refresh()
        if deleted:
            slugs = ", ".join(item["slug"] for item in deleted)
            result = (
                "✅ <b>GitHub bilan solishtirish yakunlandi.</b>\n\n"
                f"Serverdan o‘chirildi: <code>{_esc(slugs)}</code>\n"
                f"Jami: {len(deleted)} ta o‘yin.\n"
                "GitHub’da mavjud o‘yinlarga tegilmadi."
            )
        else:
            result = (
                "✅ <b>GitHub bilan solishtirish yakunlandi.</b>\n\n"
                "Tasdiqlash paytida o‘chiriladigan o‘yin qolmadi.\n"
                "GitHub’da mavjud o‘yinlarga tegilmadi."
            )
        outcome = "ok"
    except Exception as exc:
        result = await _error_text(exc)
        outcome = f"error:{exc}"
    await log_action(q.from_user.id, "GITHUB_REFRESH", "repository", outcome)
    await q.message.edit_text(result[:_TG_MAX], reply_markup=_gh_keyboard(), parse_mode="HTML")