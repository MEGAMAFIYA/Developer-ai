"""AI Developer Phase 4 — File Tools.

Features
────────
📂 Fayl yaratish   — create a new file with content (preview → confirm → write)
📄 Faylni o'qish   — read and display any file (no confirm, read-only)
✏️ Faylni tahrirlash — replace file content (diff preview → confirm → backup → write)
🗑 Faylni o'chirish — delete a file (info preview → confirm → backup → delete)

Safety rules
────────────
• All paths are resolved relative to gamehub/ and must stay inside it.
• Backup is created in gamehub/backups/ before every write/delete.
• Every mutating action is logged via action_log.
• Nothing is written until admin explicitly taps ✅ Tasdiqlash.
"""

from __future__ import annotations

import base64
import difflib
import logging

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config as cfg
from handlers.developer.modules.ai.callbacks import (
    AI_CANCEL, AI_MENU,
    AI_FILE_MANAGER,
    AI_FILE_CREATE, AI_FILE_READ, AI_FILE_EDIT, AI_FILE_DELETE,
    AI_FILE_OK, AI_FILE_PDF,
)
from handlers.developer.modules.ai.menu import ai_menu_keyboard, AI_MENU_TEXT
from handlers.developer.modules.ai.action_log import log_action
from services.project_provider import ProjectProviderError, get_project_provider
from services.pdf_export import text_to_pdf_bytes
from services.upload_service import mirror_runtime_write, mirror_runtime_delete

logger = logging.getLogger(__name__)
router = Router(name="dev:ai:file_tools")

_TG_MAX     = 4096
# Telegram bot API caps file downloads at 20MB; keep a safety margin under
# the provider's own _MAX_FILE_BYTES (8MB) for GitHub Contents API writes.
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024


# ── FSM States ────────────────────────────────────────────────────────────────

class FileCreateStates(StatesGroup):
    waiting_path    = State()
    waiting_content = State()
    confirming      = State()

class FileReadStates(StatesGroup):
    waiting_path    = State()

class FileEditStates(StatesGroup):
    waiting_path    = State()
    waiting_content = State()
    confirming      = State()

class FileDeleteStates(StatesGroup):
    waiting_path    = State()
    confirming      = State()


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
        InlineKeyboardButton(text="Tasdiqlash", callback_data=AI_FILE_OK),
        InlineKeyboardButton(text="Bekor qilish", callback_data=AI_CANCEL),
    ]])

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="AI Menyuga qaytish", callback_data=AI_MENU),
    ]])

def _file_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📂 Fayl yaratish",    callback_data=AI_FILE_CREATE),
            InlineKeyboardButton(text="📄 Faylni o'qish",    callback_data=AI_FILE_READ),
        ],
        [
            InlineKeyboardButton(text="✏️ Faylni tahrirlash", callback_data=AI_FILE_EDIT),
            InlineKeyboardButton(text="🗑 Faylni o'chirish",  callback_data=AI_FILE_DELETE),
        ],
        [InlineKeyboardButton(text="⬅️ AI Menyu",            callback_data=AI_MENU)],
    ])


# ── File Manager sub-menu entry point ─────────────────────────────────────────

@router.callback_query(lambda c: c.data == AI_FILE_MANAGER)
async def cb_file_manager_menu(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.clear()
    await q.answer()
    await q.message.edit_text(
        "📂 <b>File Manager</b>\n\n"
        "gamehub/ papkasi ichidagi fayllarni boshqarish.\n\n"
        "• Barcha yo'llar gamehub/ ga nisbatan\n"
        "• Yozish/o'chirish amallari backup bilan himoyalangan\n"
        "• Har bir amal loglarga yoziladi",
        reply_markup=_file_menu_kb(),
        parse_mode="HTML",
    )


# ── File helpers ──────────────────────────────────────────────────────────────

def _resolve(user_path: str) -> str | None:
    """Normalize a path (relative to gamehub/) and reject traversal.

    Returns the real repository path (with the ``gamehub/`` root kept),
    matching the deployed checkout layout used by services/github_service.py.
    """
    try:
        rel = get_project_provider().normalize_path(user_path)
    except ProjectProviderError:
        return None
    return rel if rel.startswith("gamehub/") else f"gamehub/{rel}"

def _diff_text(old: str, new: str, filename: str, max_lines: int = 60) -> str:
    old_l = old.splitlines(keepends=True)
    new_l = new.splitlines(keepends=True)
    diff  = list(difflib.unified_diff(old_l, new_l,
                                      fromfile=f"a/{filename}",
                                      tofile=f"b/{filename}", n=2))
    if not diff:
        return "O'zgarish yo'q."
    block = "".join(diff[:max_lines])
    if len(diff) > max_lines:
        block += f"\n... +{len(diff) - max_lines} qator"
    return block

def _send_chunks(text: str, parse_mode: str | None = None):
    """Split text into ≤4096-char list of chunks."""
    return [text[i: i + _TG_MAX] for i in range(0, max(len(text), 1), _TG_MAX)]


async def _download_document(m: Message) -> tuple[bytes, str] | None:
    """If the message carries a Telegram document, download it fully.

    Returns (raw_bytes, original_filename) or None if there's no document
    attached (the caller should then fall back to m.text). Works for ANY
    file type — PDF, HTML, .py, images, zips, etc. — since Telegram just
    hands back the raw bytes regardless of content.
    """
    doc = m.document
    if doc is None:
        return None
    if doc.file_size and doc.file_size > _MAX_UPLOAD_BYTES:
        raise ProjectProviderError(
            f"Fayl juda katta ({doc.file_size} bayt). "
            f"Chegara: {_MAX_UPLOAD_BYTES} bayt."
        )
    buf = await m.bot.download(doc, destination=None)
    raw = buf.read() if hasattr(buf, "read") else bytes(buf)
    return raw, (doc.file_name or "file")


def _try_decode_text(raw: bytes) -> str | None:
    """Return decoded text if `raw` is valid UTF-8, else None (binary)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


async def _extract_incoming_content(m: Message) -> tuple[bytes, str | None, str] | None:
    """Read the content to write from an incoming message.

    Accepts either a plain text message (typed/pasted code) or an
    uploaded Telegram document of ANY type (.pdf, .html, .py, images, ...).
    Returns (raw_bytes, decoded_text_or_None, source_label), or None if
    the message has neither text nor a document.
    """
    doc_result = await _download_document(m)
    if doc_result is not None:
        raw, filename = doc_result
        return raw, _try_decode_text(raw), f"yuklangan fayl ({filename})"
    if m.text:
        raw = m.text.encode("utf-8")
        return raw, m.text, "yozilgan matn"
    return None


# ════════════════════════════════════════════════════════════════════════════
# 📂 Fayl yaratish
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_FILE_CREATE)
async def cb_file_create_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(FileCreateStates.waiting_path)
    await q.answer()
    await q.message.edit_text(
        "<b>Fayl yaratish</b>\n\n"
        "Yangi fayl yo'lini yozing.\n"
        "Yo'l gamehub/ papkasiga nisbatan:\n\n"
        "<code>webapp/games/mygame.html</code>\n"
        "<code>services/my_service.py</code>",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


@router.message(FileCreateStates.waiting_path)
async def msg_file_create_path(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    path = _resolve(m.text or "")
    if not path:
        await m.answer("Xavfli yoki noto'g'ri yo'l. Qaytadan yozing.",
                       reply_markup=_cancel_kb())
        return
    try:
        await get_project_provider().get_file(path, preserve_repository_root=True)
    except FileNotFoundError:
        pass
    else:
        await m.answer(f"Fayl allaqachon mavjud: <code>{path}</code>\n"
                       "Tahrirlash uchun Faylni tahrirlash tugmasini ishlating.",
                       reply_markup=_cancel_kb(), parse_mode="HTML")
        return
    await state.update_data(path=path)
    await state.set_state(FileCreateStates.waiting_content)
    await m.answer(
        f"Yo'l: <code>{path}</code>\n\n"
        "Kontent yuboring (matn yoki kod):",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


@router.message(FileCreateStates.waiting_content)
async def msg_file_create_content(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    data = await state.get_data()
    path = data["path"]
    try:
        extracted = await _extract_incoming_content(m)
    except ProjectProviderError as exc:
        await m.answer(f"⚠️ {exc}", reply_markup=_cancel_kb())
        return
    if extracted is None:
        await m.answer(
            "⚠️ Matn yozing yoki istalgan turdagi faylni (pdf, html, .py, rasm...) "
            "hujjat sifatida yuboring.",
            reply_markup=_cancel_kb(),
        )
        return
    raw, text, source = extracted

    await state.update_data(content_b64=base64.b64encode(raw).decode("ascii"))
    await state.set_state(FileCreateStates.confirming)

    if text is not None:
        lines = text.splitlines()
        preview = "\n".join(lines[:30])
        if len(lines) > 30:
            preview += f"\n... +{len(lines) - 30} qator"
        body = (
            f"Qatorlar: {len(lines)}\n\n"
            f"<pre>{preview[:800]}</pre>"
        )
    else:
        body = f"Binar fayl — {len(raw)} bayt. (Matn ko'rinishida ko'rsatib bo'lmaydi.)"

    await m.answer(
        f"<b>Fayl yaratish — preview</b>\n\n"
        f"Fayl: <code>{path}</code>\n"
        f"Manba: {source}\n\n"
        f"{body}\n\n"
        "Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(), parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == AI_FILE_OK,
    StateFilter(FileCreateStates.confirming),
)
async def cb_file_create_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data    = await state.get_data()
    path    = data["path"]
    raw     = base64.b64decode(data["content_b64"])
    await state.clear()
    await q.answer()
    try:
        await get_project_provider().put_file(
            path, raw, f"Create {path}", preserve_repository_root=True
        )
        mirror_runtime_write(path, raw)  # live immediately, not just on next deploy
        rel = path
        await q.message.edit_text(
            f"✅ Fayl yaratildi va GitHub'ga yuklandi: <code>{rel}</code>\n"
            f"Hajm: {len(raw)} bayt",
            reply_markup=_back_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "FILE_CREATE", str(rel), "github_commit")
    except Exception as exc:
        await q.message.edit_text(f"Xato: <code>{exc}</code>",
                                  reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(q.from_user.id, "FILE_CREATE", str(path), f"error:{exc}")


# ════════════════════════════════════════════════════════════════════════════
# 📄 Faylni o'qish
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_FILE_READ)
async def cb_file_read_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(FileReadStates.waiting_path)
    await q.answer()
    await q.message.edit_text(
        "<b>Faylni o'qish</b>\n\n"
        "Fayl yo'lini yozing:\n\n"
        "<code>webapp/games/snake.html</code>",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


def _read_result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📑 PDF qilib yuklash", callback_data=AI_FILE_PDF)],
        [InlineKeyboardButton(text="⬅️ AI Menyuga qaytish", callback_data=AI_MENU)],
    ])


@router.message(FileReadStates.waiting_path)
async def msg_file_read(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    await state.clear()
    path = _resolve(m.text or "")
    if not path:
        await m.answer("Xavfli yoki noto'g'ri yo'l.")
        return
    try:
        await get_project_provider().get_file(path, preserve_repository_root=True)
    except FileNotFoundError:
        await m.answer(f"Fayl topilmadi: <code>{m.text}</code>",
                       parse_mode="HTML")
        return
    try:
        content = (await get_project_provider().get_file(
            path, preserve_repository_root=True
        )).content
        rel     = path
        # Kept (without an active FSM state) purely so the "PDF qilib
        # yuklash" button below knows which file to export afterwards.
        await state.update_data(pdf_path=rel)
        header  = (f"<b>Fayl:</b> <code>{rel}</code>\n"
                   f"<b>Hajm:</b> {len(content)} bayt | "
                   f"{len(content.splitlines())} qator\n\n")
        chunks  = _send_chunks(content)
        for i, chunk in enumerate(chunks):
            kb = _read_result_kb() if i == len(chunks) - 1 else None
            text = (header if i == 0 else "") + f"<pre>{chunk}</pre>"
            await m.answer(text, reply_markup=kb, parse_mode="HTML")
        await log_action(m.from_user.id, "FILE_READ", str(rel), "ok")
    except Exception as exc:
        await m.answer(f"O'qishda xato: <code>{exc}</code>",
                       reply_markup=_back_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == AI_FILE_PDF)
async def cb_file_pdf_export(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    path = data.get("pdf_path")
    if not path:
        await q.answer("Avval «Faylni o'qish» orqali bir faylni oching.", show_alert=True)
        return
    await q.answer("PDF tayyorlanmoqda...")
    try:
        content = (await get_project_provider().get_file(
            path, preserve_repository_root=True, force=True
        )).content
        pdf_bytes = text_to_pdf_bytes(content, title=path)
        filename = path.rsplit("/", 1)[-1].rsplit(".", 1)[0] + ".pdf"
        await q.message.answer_document(
            BufferedInputFile(pdf_bytes, filename=filename),
            caption=f"📑 <code>{path}</code>",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )
        await log_action(q.from_user.id, "FILE_PDF_EXPORT", path, "ok")
    except Exception as exc:
        await q.message.answer(f"PDF yaratishda xato: <code>{exc}</code>",
                               reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(q.from_user.id, "FILE_PDF_EXPORT", path, f"error:{exc}")


# ════════════════════════════════════════════════════════════════════════════
# ✏️ Faylni tahrirlash
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_FILE_EDIT)
async def cb_file_edit_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(FileEditStates.waiting_path)
    await q.answer()
    await q.message.edit_text(
        "<b>Faylni tahrirlash</b>\n\n"
        "Tahrirlash uchun fayl yo'lini yozing:\n\n"
        "<code>webapp/games/snake.html</code>",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


@router.message(FileEditStates.waiting_path)
async def msg_file_edit_path(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    path = _resolve(m.text or "")
    if not path:
        await m.answer("Xavfli yoki noto'g'ri yo'l.", reply_markup=_cancel_kb())
        return
    try:
        await get_project_provider().get_file(path, preserve_repository_root=True)
    except FileNotFoundError:
        await m.answer(f"Fayl topilmadi: <code>{m.text}</code>",
                       reply_markup=_cancel_kb(), parse_mode="HTML")
        return
    try:
        old_content = (await get_project_provider().get_file(
            path, preserve_repository_root=True
        )).content
        rel         = path
        await state.update_data(path=path, old_content=old_content)
        await state.set_state(FileEditStates.waiting_content)
        preview = "\n".join(old_content.splitlines()[:20])
        if len(old_content.splitlines()) > 20:
            preview += f"\n... +{len(old_content.splitlines())-20} qator"
        await m.answer(
            f"Fayl: <code>{rel}</code>\n"
            f"Joriy kontent ({len(old_content.splitlines())} qator):\n"
            f"<pre>{preview[:600]}</pre>\n\n"
            "Yangi kontent yuboring (to'liq fayl):",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
    except Exception as exc:
        await m.answer(f"O'qishda xato: <code>{exc}</code>",
                       reply_markup=_cancel_kb(), parse_mode="HTML")


@router.message(FileEditStates.waiting_content)
async def msg_file_edit_content(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    data        = await state.get_data()
    path        = data["path"]
    old_content = data["old_content"]

    try:
        extracted = await _extract_incoming_content(m)
    except ProjectProviderError as exc:
        await m.answer(f"⚠️ {exc}", reply_markup=_cancel_kb())
        return
    if extracted is None:
        await m.answer(
            "⚠️ Yangi matn yozing yoki istalgan turdagi faylni (pdf, html, .py, rasm...) "
            "hujjat sifatida yuboring.",
            reply_markup=_cancel_kb(),
        )
        return
    raw, new_text, source = extracted

    await state.update_data(content_b64=base64.b64encode(raw).decode("ascii"))
    await state.set_state(FileEditStates.confirming)

    if new_text is not None:
        diff = _diff_text(old_content, new_text, path.rsplit("/", 1)[-1])
        diff_preview = diff[:1200]
        if len(diff) > 1200:
            diff_preview += "\n..."
        body = (
            f"Eski: {len(old_content.splitlines())} qator  "
            f"Yangi: {len(new_text.splitlines())} qator\n\n"
            f"<pre>{diff_preview}</pre>"
        )
    else:
        body = f"Binar fayl bilan almashtiriladi — {len(raw)} bayt. (Diff ko'rsatib bo'lmaydi.)"

    await m.answer(
        f"<b>Faylni tahrirlash — preview</b>\n\n"
        f"Fayl: <code>{path}</code>\n"
        f"Manba: {source}\n\n"
        f"{body}\n\n"
        "GitHub commit yaratiladi. Tasdiqlaysizmi?",
        reply_markup=_confirm_kb(), parse_mode="HTML",
    )


@router.callback_query(
    lambda c: c.data == AI_FILE_OK,
    StateFilter(FileEditStates.confirming),
)
async def cb_file_edit_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    path = data["path"]
    raw  = base64.b64decode(data["content_b64"])
    await state.clear()
    await q.answer()
    try:
        await get_project_provider().put_file(
            path, raw, f"Edit {path}", preserve_repository_root=True
        )
        mirror_runtime_write(path, raw)  # live immediately, not just on next deploy
        rel = path
        await q.message.edit_text(
            f"✅ Fayl yangilandi va GitHub'ga yuklandi: <code>{rel}</code>\n"
            f"Hajm: {len(raw)} bayt. Oldingi versiya GitHub tarixida saqlandi.",
            reply_markup=_back_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "FILE_EDIT", str(rel), "github_commit")
    except Exception as exc:
        await q.message.edit_text(f"Xato: <code>{exc}</code>",
                                  reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(q.from_user.id, "FILE_EDIT", str(path), f"error:{exc}")


# ════════════════════════════════════════════════════════════════════════════
# 🗑 Faylni o'chirish
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda c: c.data == AI_FILE_DELETE)
async def cb_file_delete_start(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    await state.set_state(FileDeleteStates.waiting_path)
    await q.answer()
    await q.message.edit_text(
        "<b>Faylni o'chirish</b>\n\n"
        "O'chirish uchun fayl yo'lini yozing:\n\n"
        "<code>webapp/games/old_game.html</code>",
        reply_markup=_cancel_kb(), parse_mode="HTML",
    )


@router.message(FileDeleteStates.waiting_path)
async def msg_file_delete_path(m: Message, state: FSMContext) -> None:
    if not await _guard_msg(m):
        return
    path = _resolve(m.text or "")
    if not path:
        await m.answer("Xavfli yoki noto'g'ri yo'l.", reply_markup=_cancel_kb())
        return
    try:
        file = await get_project_provider().get_file(path, preserve_repository_root=True)
    except FileNotFoundError:
        await m.answer(f"Fayl topilmadi: <code>{m.text}</code>",
                       reply_markup=_cancel_kb(), parse_mode="HTML")
        return
    try:
        size = file.size
        rel  = path
        await state.update_data(path=path)
        await state.set_state(FileDeleteStates.confirming)
        await m.answer(
            f"<b>O'chirish — preview</b>\n\n"
            f"Fayl: <code>{rel}</code>\n"
            f"Hajm: {size} bayt\n\n"
            "GitHub commit tarixi saqlanadi.\n"
            "<b>Bu amal qaytarilmaydi!</b>\n\n"
            "Tasdiqlaysizmi?",
            reply_markup=_confirm_kb(), parse_mode="HTML",
        )
    except Exception as exc:
        await m.answer(f"Xato: <code>{exc}</code>",
                       reply_markup=_cancel_kb(), parse_mode="HTML")


@router.callback_query(
    lambda c: c.data == AI_FILE_OK,
    StateFilter(FileDeleteStates.confirming),
)
async def cb_file_delete_confirm(q: CallbackQuery, state: FSMContext) -> None:
    if not await _guard_cb(q):
        return
    data = await state.get_data()
    path = data["path"]
    await state.clear()
    await q.answer()
    try:
        await get_project_provider().delete_file(
            path, f"Delete {path}", preserve_repository_root=True
        )
        mirror_runtime_delete(path)  # keep the live server in sync too
        rel    = path
        await q.message.edit_text(
            f"Fayl o'chirildi: <code>{rel}</code>\n"
            "Oldingi versiya GitHub commit tarixida saqlandi.",
            reply_markup=_back_kb(), parse_mode="HTML",
        )
        await log_action(q.from_user.id, "FILE_DELETE", str(rel), "github_commit")
    except Exception as exc:
        await q.message.edit_text(f"Xato: <code>{exc}</code>",
                                  reply_markup=_back_kb(), parse_mode="HTML")
        await log_action(q.from_user.id, "FILE_DELETE", str(path), f"error:{exc}")


# ── Shared: AI_FILE_OK with no known state → ignore gracefully ───────────────
# (covered by module-level confirm handlers above via StateFilter)
