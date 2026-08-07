"""Developer Mode › ⚙️ Sozlamalar

Features
────────
👁 Ko'rish          — joriy konfiguratsiyani ko'rsatish (maxfiy qiymatlar yashiriladi)
🔧 Maintenance Mode — yoqish/o'chirish (DB settings jadvalida saqlanadi)
🌐 WebApp URL       — joriy URL ni ko'rish va o'zgartirish (FSM)
"""

from __future__ import annotations

import logging

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
from database.global_db import get_setting, set_setting
from handlers.developer.callbacks import (
    DEV_SETTINGS,
    DEV_SET_VIEW,
    DEV_SET_MAINT_ON,
    DEV_SET_MAINT_OFF,
    DEV_SET_WEBAPP,
    DEV_SET_WEBAPP_OK,
    DEV_SET_WEBAPP_NO,
    DEV_SET_GITHUB,
    DEV_SET_GITHUB_OK,
    DEV_SET_GITHUB_NO,
    DEV_SET_GITHUB_REFRESH,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:settings")

_TG_MAX   = 4096
_MAINT_KEY = "maintenance_mode"
_WEBAPP_KEY = "webapp_url_override"


# ── FSM ───────────────────────────────────────────────────────────────────────

class SettingsFSM(StatesGroup):
    waiting_webapp_url = State()
    waiting_github = State()


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

async def _settings_keyboard() -> InlineKeyboardMarkup:
    maint = await get_setting(_MAINT_KEY) or "0"
    maint_is_on = maint == "1"
    maint_btn = (
        InlineKeyboardButton(text="🔴 Maintenance: YOQIQ", callback_data=DEV_SET_MAINT_OFF)
        if maint_is_on else
        InlineKeyboardButton(text="🟢 Maintenance: O'CHIQ", callback_data=DEV_SET_MAINT_ON)
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁 Ko'rish",      callback_data=DEV_SET_VIEW),
            InlineKeyboardButton(text="🌐 WebApp URL",   callback_data=DEV_SET_WEBAPP),
        ],
        [InlineKeyboardButton(text="🐙 GitHub loyiha", callback_data=DEV_SET_GITHUB)],
        [maint_btn],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="dev:menu")],
    ])


def _confirm_webapp_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Saqlash", callback_data=DEV_SET_WEBAPP_OK),
        InlineKeyboardButton(text="❌ Bekor",   callback_data=DEV_SET_WEBAPP_NO),
    ]])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(val: str) -> str:
    """Hide sensitive values."""
    if not val:
        return "<i>bo'sh</i>"
    if len(val) <= 8:
        return "***"
    return val[:4] + "…" + val[-4:]


async def _config_text() -> str:
    maint     = await get_setting(_MAINT_KEY)  or "0"
    wa_over   = await get_setting(_WEBAPP_KEY) or ""
    maint_lbl = "🔴 YOQIQ" if maint == "1" else "🟢 O'CHIQ"

    # AI settings from DB
    ai_prov = await get_setting("ai_provider")  or cfg.config.AI_PROVIDER or "—"
    ai_mod  = await get_setting("ai_model")     or cfg.config.AI_MODEL     or "—"
    ai_key  = await get_setting("ai_api_key")   or cfg.config.AI_API_KEY
    ai_key_disp = _mask(ai_key) if ai_key else "<i>yo'q</i>"
    gh_owner = await get_setting("github_owner") or cfg.config.GITHUB_OWNER or "—"
    gh_repo = await get_setting("github_repo") or cfg.config.GITHUB_REPO or "—"
    gh_branch = await get_setting("github_branch") or cfg.config.GITHUB_BRANCH or "main"
    gh_token = "✅ o'rnatilgan" if cfg.config.GITHUB_TOKEN else "❌ secret yo'q"

    lines = [
        "⚙️ <b>Joriy konfiguratsiya</b>\n",
        f"🤖 Bot:           <code>@{cfg.config.BOT_USERNAME or '?'}</code>",
        f"👤 Admin ID:      <code>{cfg.config.ADMIN_ID}</code>",
        f"🌐 WebApp URL:    <code>{wa_over or cfg.config.WEBAPP_URL}</code>",
        f"🔧 Maintenance:   {maint_lbl}",
        "",
        "🤖 <b>AI Sozlamalar</b>",
        f"Provider: <code>{ai_prov}</code>",
        f"Model:    <code>{ai_mod}</code>",
        f"API Key:  {ai_key_disp}",
        "",
        "🐙 <b>GitHub loyiha</b>",
        f"Owner:  <code>{gh_owner}</code>",
        f"Repo:   <code>{gh_repo}</code>",
        f"Branch: <code>{gh_branch}</code>",
        f"Token:  {gh_token}",
    ]
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_SETTINGS)
async def cb_settings_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await q.message.edit_text(
        "⚙️ <b>Sozlamalar</b>\n\nBot sozlamalarini boshqarish.",
        reply_markup=await _settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_SET_VIEW)
async def cb_set_view(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    text = await _config_text()
    await q.message.edit_text(
        text[:_TG_MAX],
        reply_markup=await _settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_SET_MAINT_ON)
async def cb_maint_on(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await set_setting(_MAINT_KEY, "1")
    await log_action(q.from_user.id, "SETTINGS_MAINT", "maintenance_mode", "on")
    await q.answer("🔴 Maintenance Mode yoqildi")
    await q.message.edit_text(
        "⚙️ <b>Sozlamalar</b>\n\n🔴 Maintenance Mode <b>yoqildi</b>.",
        reply_markup=await _settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_SET_MAINT_OFF)
async def cb_maint_off(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await set_setting(_MAINT_KEY, "0")
    await log_action(q.from_user.id, "SETTINGS_MAINT", "maintenance_mode", "off")
    await q.answer("🟢 Maintenance Mode o'chirildi")
    await q.message.edit_text(
        "⚙️ <b>Sozlamalar</b>\n\n🟢 Maintenance Mode <b>o'chirildi</b>.",
        reply_markup=await _settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_SET_WEBAPP)
async def cb_set_webapp_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    current = await get_setting(_WEBAPP_KEY) or cfg.config.WEBAPP_URL
    await state.set_state(SettingsFSM.waiting_webapp_url)
    await q.message.edit_text(
        f"🌐 <b>WebApp URL</b>\n\n"
        f"Joriy URL: <code>{current}</code>\n\n"
        "Yangi URL ni kiriting (https:// bilan boshlanishi kerak):",
        reply_markup=back_keyboard("❌ Bekor"),
        parse_mode="HTML",
    )


@router.message(StateFilter(SettingsFSM.waiting_webapp_url))
async def msg_set_webapp(m: Message, state: FSMContext) -> None:
    if not _is_admin(m.from_user.id):
        return
    url = (m.text or "").strip()
    if not url.startswith("http"):
        await m.answer(
            "⛔ URL <code>https://</code> bilan boshlanishi kerak.",
            parse_mode="HTML",
        )
        return
    await state.update_data(new_url=url)
    await state.set_state(SettingsFSM.waiting_webapp_url)
    # store for confirm step
    await state.update_data(new_url=url, confirmed=False)
    await m.answer(
        f"🌐 Yangi URL: <code>{url}</code>\n\nSaqlaysizmi?",
        reply_markup=_confirm_webapp_kb(),
        parse_mode="HTML",
    )


@router.callback_query(StateFilter(SettingsFSM.waiting_webapp_url),
                        lambda c: c.data == DEV_SET_WEBAPP_OK)
async def cb_set_webapp_ok(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data = await state.get_data()
    url  = data.get("new_url", "")
    await state.clear()
    if not url:
        await q.answer("URL topilmadi.", show_alert=True)
        return
    try:
        await set_setting(_WEBAPP_KEY, url)
        await log_action(q.from_user.id, "SETTINGS_WEBAPP", "webapp_url_override", url[:80])
        await q.answer("✅ URL saqlandi")
        await q.message.edit_text(
            f"✅ WebApp URL yangilandi:\n<code>{url}</code>",
            reply_markup=await _settings_keyboard(),
            parse_mode="HTML",
        )
    except Exception as exc:
        await q.message.edit_text(
            f"❌ Saqlashda xato: {exc}",
            reply_markup=await _settings_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(StateFilter(SettingsFSM.waiting_webapp_url),
                        lambda c: c.data == DEV_SET_WEBAPP_NO)
async def cb_set_webapp_no(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    await q.message.edit_text(
        "⚙️ <b>Sozlamalar</b>",
        reply_markup=await _settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_SET_GITHUB)
async def cb_set_github_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    owner = await get_setting("github_owner") or cfg.config.GITHUB_OWNER or ""
    repo = await get_setting("github_repo") or cfg.config.GITHUB_REPO or ""
    branch = await get_setting("github_branch") or cfg.config.GITHUB_BRANCH or "main"
    await state.set_state(SettingsFSM.waiting_github)
    await q.message.edit_text(
        "🐙 <b>GitHub loyiha sozlamalari</b>\n\n"
        f"Joriy: <code>{owner}/{repo}@{branch}</code>\n\n"
        "Quyidagi formatda yuboring:\n"
        "<code>owner/repository branch</code>\n\n"
        "Masalan: <code>my-org/gamehub main</code>\n"
        "Token Telegram orqali kiritilmaydi — GITHUB_TOKEN secret sifatida saqlanadi.",
        reply_markup=back_keyboard("❌ Bekor"),
        parse_mode="HTML",
    )


@router.message(StateFilter(SettingsFSM.waiting_github))
async def msg_set_github(m: Message, state: FSMContext) -> None:
    if not _is_admin(m.from_user.id):
        return
    raw = (m.text or "").strip()
    parts = raw.split()
    if len(parts) != 2 or "/" not in parts[0] or not all(parts):
        await m.answer(
            "⛔ Format noto'g'ri. Masalan: <code>my-org/gamehub main</code>",
            parse_mode="HTML",
        )
        return
    owner, repo = parts[0].split("/", 1)
    if not owner or not repo or repo.endswith(".git"):
        repo = repo.removesuffix(".git")
    await state.update_data(github_owner=owner, github_repo=repo, github_branch=parts[1])
    await m.answer(
        f"🐙 <b>GitHub sozlamalari</b>\n\n"
        f"Owner: <code>{owner}</code>\n"
        f"Repo: <code>{repo}</code>\n"
        f"Branch: <code>{parts[1]}</code>\n\n"
        "Saqlaysizmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Saqlash", callback_data=DEV_SET_GITHUB_OK),
            InlineKeyboardButton(text="❌ Bekor", callback_data=DEV_SET_GITHUB_NO),
        ]]),
        parse_mode="HTML",
    )


@router.callback_query(
    StateFilter(SettingsFSM.waiting_github),
    lambda c: c.data == DEV_SET_GITHUB_OK,
)
async def cb_set_github_ok(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data = await state.get_data()
    await state.clear()
    try:
        await set_setting("github_owner", data["github_owner"])
        await set_setting("github_repo", data["github_repo"])
        await set_setting("github_branch", data["github_branch"])
        await q.answer("✅ GitHub sozlamalari saqlandi")
        await q.message.edit_text(
            "✅ GitHub loyiha sozlamalari saqlandi.\n"
            "Token GITHUB_TOKEN secretidan olinadi.",
            reply_markup=await _settings_keyboard(),
            parse_mode="HTML",
        )
        await log_action(q.from_user.id, "SETTINGS_GITHUB", "repository", "updated")
    except Exception as exc:
        await q.message.edit_text(
            f"❌ Saqlashda xato: <code>{exc}</code>",
            reply_markup=await _settings_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(
    StateFilter(SettingsFSM.waiting_github),
    lambda c: c.data == DEV_SET_GITHUB_NO,
)
async def cb_set_github_no(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    await q.message.edit_text(
        "⚙️ <b>Sozlamalar</b>",
        reply_markup=await _settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == DEV_SET_GITHUB_REFRESH)
async def cb_set_github_refresh(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    from services.project_provider import get_project_provider
    try:
        entries = await get_project_provider().refresh()
        await q.answer(f"✅ Cache yangilandi: {len(entries)} ta entry")
    except Exception as exc:
        await q.answer(f"❌ {str(exc)[:180]}", show_alert=True)
