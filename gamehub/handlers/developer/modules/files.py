"""Developer Mode › 📂 Fayl Menejeri

Features
────────
📋 Fayllar ro'yxati — webapp/games/ katalogidagi HTML fayllar
👁 Ko'rish           — fayl mazmunini ko'rish (birinchi 3000 belgi)
📥 Yuklab olish      — faylni Telegram document sifatida yuborish
🗑 O'chirish         — tasdiq bilan o'chirish (FSM)
📤 Yuklash           — yangi HTML fayl yuklash (document orqali)
"""

from __future__ import annotations

import html as _html
import io
import logging

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from database.global_db import delete_game_by_html_file, is_image_url_shared
from database.game_db import delete_scores_by_game_name
from handlers.developer.callbacks import (
    DEV_FILES,
    DEV_FILES_LIST,
    DEV_FILES_DEL_OK,
    DEV_FILES_DEL_NO,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action
from services.project_provider import ProjectProviderError, get_project_provider

logger = logging.getLogger(__name__)
router = Router(name="dev:files")

_GAMES_DIR = "webapp/games"
_TG_MAX    = 4096
_VIEW_PFX  = "dev:files:view:"    # dynamic: dev:files:view:<filename>
_DEL_PFX   = "dev:files:del:"     # dynamic: dev:files:del:<filename>
_DL_PFX    = "dev:files:dl:"      # dynamic: dev:files:dl:<filename>


# ── FSM ───────────────────────────────────────────────────────────────────────

class FilesFSM(StatesGroup):
    pending_delete = State()   # stores filename in state data
    waiting_upload = State()   # expects a Document message


# ── Guard ─────────────────────────────────────────────────────────────────────

def _is_admin(uid: int) -> bool:
    return uid == cfg.config.ADMIN_ID


async def _guard(q: CallbackQuery) -> bool:
    if _is_admin(q.from_user.id):
        return True
    await q.answer("⛔ Ruxsat yo'q.", show_alert=True)
    return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _files_keyboard(files: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for name in files:
        rows.append([
            InlineKeyboardButton(text=f"📄 {name}",        callback_data=f"{_VIEW_PFX}{name}"),
            InlineKeyboardButton(text="📥",                callback_data=f"{_DL_PFX}{name}"),
            InlineKeyboardButton(text="🗑",                callback_data=f"{_DEL_PFX}{name}"),
        ])
    rows.append([
        InlineKeyboardButton(text="📤 Fayl yuklash", callback_data="dev:files:upload"),
        InlineKeyboardButton(text="⬅️ Orqaga",       callback_data="dev:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_del_kb(filename: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Ha, o'chir",    callback_data=DEV_FILES_DEL_OK),
        InlineKeyboardButton(text="❌ Bekor",          callback_data=DEV_FILES_DEL_NO),
    ]])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _list_files() -> list[dict]:
    entries = await get_project_provider().list_files(_GAMES_DIR)
    allowed = {".html", ".js", ".css", ".json", ".py", ".svg", ".txt"}
    return [
        {"name": entry.path.rsplit("/", 1)[-1], "path": entry.path, "size": entry.size}
        for entry in entries
        if entry.kind == "file"
        and "." + entry.path.rsplit(".", 1)[-1].lower() in allowed
    ]


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def _files_text(files: list[dict]) -> str:
    if not files:
        return (
            "📂 <b>Fayl Menejeri</b>\n\n"
            f"<code>{_GAMES_DIR}/</code>\n\n"
            "Hech qanday fayl topilmadi."
        )
    lines = [
        f"📂 <b>Fayl Menejeri</b> ({len(files)} ta fayl)\n",
        f"<code>{_GAMES_DIR}/</code>\n",
    ]
    for file in files:
        lines.append(
            f"  📄 {_html.escape(file['path'])} "
            f"<i>({_fmt_size(file['size'])})</i>"
        )
    lines.append("\n📌 Faylni bosib ko'rish, yuklab olish yoki o'chirish mumkin.")
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data in (DEV_FILES, DEV_FILES_LIST))
async def cb_files_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    try:
        files = await _list_files()
    except Exception as exc:
        files = []
        logger.warning("GitHub file listing failed: %s", exc)
    await q.message.edit_text(
        _files_text(files)[:_TG_MAX],
        reply_markup=_files_keyboard(files),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith(_VIEW_PFX))
async def cb_file_view(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    filename = q.data[len(_VIEW_PFX):]
    try:
        file = await get_project_provider().get_file(filename)
    except (FileNotFoundError, ProjectProviderError):
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer()
    try:
        content = file.content
        snippet = content[:3000]
        truncation = f"\n\n… (yana {len(content)-3000} belgi)" if len(content) > 3000 else ""
        # Escape so Telegram's HTML parser never interprets file contents as markup
        escaped = _html.escape(snippet) + (_html.escape(truncation) if truncation else "")
        text = (
            f"📄 <b>{_html.escape(filename)}</b>\n"
            f"<i>{_fmt_size(file.size)}</i>\n\n"
            f"<pre>{escaped[:3800]}</pre>"
        )
    except Exception as exc:
        text = f"❌ O'qishda xato: {_html.escape(str(exc))}"
    await q.message.edit_text(
        text[:_TG_MAX],
        reply_markup=back_keyboard("⬅️ Ro'yxatga qaytish"),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith(_DL_PFX))
async def cb_file_download(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    filename = q.data[len(_DL_PFX):]
    try:
        raw, _ = await get_project_provider().get_file_bytes(filename)
    except (FileNotFoundError, ProjectProviderError):
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer("⏳ Yuklanmoqda…")
    try:
        await q.message.answer_document(
            BufferedInputFile(raw, filename=filename.rsplit("/", 1)[-1]),
            caption=f"📥 {filename} ({_fmt_size(len(raw))})",
        )
        await log_action(q.from_user.id, "FILE_DOWNLOAD", filename, "ok")
    except Exception as exc:
        await q.message.answer(f"❌ Yuborishda xato: {exc}")


@router.callback_query(
    lambda c: c.data.startswith(_DEL_PFX)
    and c.data not in (DEV_FILES_DEL_OK, DEV_FILES_DEL_NO)
)
async def cb_file_delete_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    filename = q.data[len(_DEL_PFX):]
    try:
        file = await get_project_provider().get_file(filename)
    except (FileNotFoundError, ProjectProviderError):
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer()
    await state.set_state(FilesFSM.pending_delete)
    await state.update_data(filename=filename)
    await q.message.edit_text(
        f"🗑 <b>O'chirishni tasdiqlang</b>\n\n"
        f"Fayl: <code>{_html.escape(filename)}</code>\n"
        f"O'lcham: {_fmt_size(file.size)}\n\n"
        "⚠️ Bu amalni qaytarib bo'lmaydi!",
        reply_markup=_confirm_del_kb(filename),
        parse_mode="HTML",
    )


@router.callback_query(StateFilter(FilesFSM.pending_delete), lambda c: c.data == DEV_FILES_DEL_OK)
async def cb_file_delete_ok(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    data = await state.get_data()
    filename = data.get("filename", "")
    await state.clear()
    try:
        file = await get_project_provider().get_file(filename, force=True)
        size = file.size
        await get_project_provider().delete_file(filename, f"Delete {filename}")

        # Keep the game registry in sync: hard-delete every DB record that
        # points to this HTML file, then remove any now-orphaned local image,
        # and finally purge all score rows for every deleted game slug so that
        # Statistics, leaderboards, and /reyting show no orphaned data.
        deleted_slugs: list[str] = []
        if filename.endswith(".html"):
            try:
                deleted_rows = await delete_game_by_html_file(filename)
                deleted_slugs = [r["slug"] for r in deleted_rows]

                # FIX #3 — purge scores for every deleted slug.
                for slug in deleted_slugs:
                    try:
                        n = await delete_scores_by_game_name(slug)
                        logger.info(
                            "Purged %s score row(s) for deleted game=%s", n, slug
                        )
                    except Exception as score_exc:
                        logger.warning(
                            "Could not purge scores for game=%s: %s", slug, score_exc
                        )

            except Exception as db_exc:
                logger.warning("Could not delete game record for %s: %s", filename, db_exc)

        log_detail = f"size={size}"
        if deleted_slugs:
            log_detail += f" deleted_slugs={','.join(deleted_slugs)}"
        await log_action(q.from_user.id, "FILE_DELETE", filename, log_detail)
        await q.answer(f"✅ {filename} o'chirildi")
    except Exception as exc:
        await q.answer(f"❌ Xato: {exc}", show_alert=True)
        return
    files = await _list_files()
    await q.message.edit_text(
        _files_text(files)[:_TG_MAX],
        reply_markup=_files_keyboard(files),
        parse_mode="HTML",
    )


@router.callback_query(StateFilter(FilesFSM.pending_delete), lambda c: c.data == DEV_FILES_DEL_NO)
async def cb_file_delete_no(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    files = await _list_files()
    await q.message.edit_text(
        _files_text(files)[:_TG_MAX],
        reply_markup=_files_keyboard(files),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == "dev:files:upload")
async def cb_file_upload_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    await q.answer()
    await state.set_state(FilesFSM.waiting_upload)
    await q.message.edit_text(
        "📤 <b>Fayl yuklash</b>\n\n"
        "HTML, JS, CSS yoki JSON faylni document sifatida yuboring.\n"
        "Fayl <code>webapp/games/</code> papkasiga saqlanadi.\n\n"
        "⚠️ Mavjud fayl ustiga yozilsa, eski fayl o'chadi!",
        reply_markup=back_keyboard("❌ Bekor"),
        parse_mode="HTML",
    )


@router.message(StateFilter(FilesFSM.waiting_upload), F.document)
async def msg_file_upload(m: Message, state: FSMContext) -> None:
    if not _is_admin(m.from_user.id):
        return
    await state.clear()
    doc = m.document
    if not doc:
        await m.answer("❌ Hujjat topilmadi.")
        return
    filename = doc.file_name or "uploaded_file"
    allowed  = (".html", ".js", ".css", ".json")
    if not any(filename.endswith(ext) for ext in allowed):
        await m.answer(
            f"⛔ Ruxsat etilgan kengaytmalar: {', '.join(allowed)}",
            reply_markup=back_keyboard(),
        )
        return
    try:
        buffer = io.BytesIO()
        await m.bot.download(doc, destination=buffer)
        raw = buffer.getvalue()
        await get_project_provider().put_file(
            f"{_GAMES_DIR}/{filename}",
            raw,
            f"Upload {filename}",
        )
        await log_action(m.from_user.id, "FILE_UPLOAD", filename,
                         f"size={len(raw)}")

        await m.answer(
            f"✅ <b>{filename}</b> muvaffaqiyatli yuklandi!\n"
            f"O'lcham: {_fmt_size(len(raw))}",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
    except Exception as exc:
        logger.error("file upload error: %s", exc)
        await m.answer(f"❌ Yuklashda xato: {exc}", reply_markup=back_keyboard())


@router.message(StateFilter(FilesFSM.waiting_upload))
async def msg_file_upload_wrong(m: Message, state: FSMContext) -> None:
    if not _is_admin(m.from_user.id):
        return
    await m.answer(
        "⚠️ Iltimos, faylni <b>document</b> sifatida yuboring.",
        parse_mode="HTML",
    )
