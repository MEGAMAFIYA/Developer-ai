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

import logging
from pathlib import Path

from aiogram import Router, F
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
    DEV_FILES,
    DEV_FILES_LIST,
    DEV_FILES_DEL_OK,
    DEV_FILES_DEL_NO,
)
from handlers.developer.keyboards import back_keyboard
from handlers.developer.modules.ai.action_log import log_action

logger = logging.getLogger(__name__)
router = Router(name="dev:files")

_BASE      = Path(__file__).resolve().parents[3]          # gamehub/
_GAMES_DIR = _BASE / "webapp" / "games"
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

def _list_files() -> list[str]:
    if not _GAMES_DIR.exists():
        return []
    return sorted(
        f.name for f in _GAMES_DIR.iterdir()
        if f.is_file() and f.suffix in (".html", ".js", ".css", ".json")
    )


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def _files_text(files: list[str]) -> str:
    if not files:
        return (
            "📂 <b>Fayl Menejeri</b>\n\n"
            f"<code>{_GAMES_DIR}</code>\n\n"
            "Hech qanday fayl topilmadi."
        )
    lines = [
        f"📂 <b>Fayl Menejeri</b> ({len(files)} ta fayl)\n",
        f"<code>{_GAMES_DIR}</code>\n",
    ]
    for name in files:
        path = _GAMES_DIR / name
        size = _fmt_size(path.stat().st_size) if path.exists() else "?"
        lines.append(f"  📄 {name} <i>({size})</i>")
    lines.append("\n📌 Faylni bosib ko'rish, yuklab olish yoki o'chirish mumkin.")
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data in (DEV_FILES, DEV_FILES_LIST))
async def cb_files_main(q: CallbackQuery) -> None:
    if not await _guard(q):
        return
    await q.answer()
    files = _list_files()
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
    path = _GAMES_DIR / filename
    if not path.exists() or not path.is_file():
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer()
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        preview = content[:3000]
        if len(content) > 3000:
            preview += f"\n\n… (yana {len(content)-3000} belgi)"
        text = (
            f"📄 <b>{filename}</b>\n"
            f"<i>{_fmt_size(path.stat().st_size)}</i>\n\n"
            f"<pre>{preview[:3800]}</pre>"
        )
    except Exception as exc:
        text = f"❌ O'qishda xato: {exc}"
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
    path = _GAMES_DIR / filename
    if not path.exists():
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer("⏳ Yuklanmoqda…")
    try:
        await q.message.answer_document(
            FSInputFile(path, filename=filename),
            caption=f"📥 {filename} ({_fmt_size(path.stat().st_size)})",
        )
        await log_action(q.from_user.id, "FILE_DOWNLOAD", filename, "ok")
    except Exception as exc:
        await q.message.answer(f"❌ Yuborishda xato: {exc}")


@router.callback_query(lambda c: c.data.startswith(_DEL_PFX))
async def cb_file_delete_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(q):
        return
    filename = q.data[len(_DEL_PFX):]
    path = _GAMES_DIR / filename
    if not path.exists():
        await q.answer("Fayl topilmadi.", show_alert=True)
        return
    await q.answer()
    await state.set_state(FilesFSM.pending_delete)
    await state.update_data(filename=filename)
    await q.message.edit_text(
        f"🗑 <b>O'chirishni tasdiqlang</b>\n\n"
        f"Fayl: <code>{filename}</code>\n"
        f"O'lcham: {_fmt_size(path.stat().st_size)}\n\n"
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
    path = _GAMES_DIR / filename
    try:
        size = path.stat().st_size if path.exists() else 0
        path.unlink(missing_ok=True)
        await log_action(q.from_user.id, "FILE_DELETE", filename, f"size={size}")
        await q.answer(f"✅ {filename} o'chirildi")
    except Exception as exc:
        await q.answer(f"❌ Xato: {exc}", show_alert=True)
        return
    files = _list_files()
    await q.message.edit_text(
        _files_text(files)[:_TG_MAX],
        reply_markup=_files_keyboard(files),
        parse_mode="HTML",
    )


@router.callback_query(StateFilter(FilesFSM.pending_delete), lambda c: c.data == DEV_FILES_DEL_NO)
async def cb_file_delete_no(q: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await q.answer("Bekor qilindi")
    files = _list_files()
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
    dest = _GAMES_DIR / filename
    _GAMES_DIR.mkdir(parents=True, exist_ok=True)
    try:
        await m.bot.download(doc, destination=str(dest))
        await log_action(m.from_user.id, "FILE_UPLOAD", filename,
                         f"size={dest.stat().st_size}")
        await m.answer(
            f"✅ <b>{filename}</b> muvaffaqiyatli yuklandi!\n"
            f"O'lcham: {_fmt_size(dest.stat().st_size)}",
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
