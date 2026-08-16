"""Developer Mode — /developer command + main menu navigation."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config as cfg
from handlers.developer.callbacks import DEV_MENU, DEV_CLOSE
from handlers.developer.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router(name="dev:menu")

MENU_TEXT = (
    "🧑‍💻 <b>Developer Mode</b>\n\n"
    "Xush kelibsiz! Quyidagi bo'limlardan birini tanlang:\n\n"
    "🎮 <b>O'yinlar</b> — o'yinlaringiz ro'yxatini ko'rasiz; har birini "
    "bir tugma bilan yoqib/o'chirib, foydalanuvchilarga ko'rinmas "
    "(yashirin) qilib qo'yishingiz mumkin.\n\n"
    "🤖 <b>AI Developer</b> — AI yordamida kod yozdirish, mavjud o'yin "
    "kodini tahrirlash, tahlil qilish, xato topish/tuzatish va loyiha "
    "fayllari bilan (o'qish/yaratish/tahrirlash/o'chirish, GitHub'ga "
    "to'g'ridan-to'g'ri) ishlash.\n\n"
    "🤖 <b>Buyruqlar</b> — botning Telegram buyruqlar ro'yxatini "
    "(/start, /help va h.k.) o'rnatish yoki tozalash.\n\n"
    "📂 <b>Fayllar</b> — o'yin fayllarini (HTML/JS/CSS) ko'rish, "
    "yuklash, tahrirlash va o'chirish — barchasi to'g'ridan-to'g'ri "
    "GitHub'ga yoziladi.\n\n"
    "🗄 <b>Database</b> — bazadagi jadvallarni ko'rish, faqat-o'qish "
    "SQL so'rov yuborish, CSV eksport va tozalash (VACUUM).\n\n"
    "📊 <b>Statistika</b> — foydalanuvchilar, o'yinlar va natijalar "
    "bo'yicha umumiy ko'rsatkichlar.\n\n"
    "🌐 <b>GitHub</b> — repozitoriy holati, so'nggi commitlar va "
    "GitHub'dan yangilanishlarni tekshirish.\n\n"
    "⚙️ <b>Sozlamalar</b> — joriy konfiguratsiyani ko'rish, Maintenance "
    "rejimi va WebApp URL'ni o'zgartirish.\n\n"
    "🧪 <b>Test</b> — baza, WebApp, bot va natija saqlash tizimlarini "
    "sinovdan o'tkazish.\n\n"
    "📜 <b>Loglar</b> — bot loglarini ko'rish, daraja/sana bo'yicha "
    "filtrlash, qidirish, yuklab olish va tozalash.\n\n"
    "🔄 <b>Backup</b> — bazadagi o'yinlar va natijalarni JSON/CSV "
    "ko'rinishida zaxira nusxalash.\n\n"
    "📦 <b>Project Manager</b> — butun loyiha kodini (GitHub'dan) "
    "ko'rish, fayl/matn bo'yicha qidirish, vaqtinchalik fayllarni "
    "tozalash va to'liq loyihani ZIP qilib eksport qilish."
)


# ── Guard: only ADMIN_ID may use this router ─────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == cfg.config.ADMIN_ID


# ── /developer command ────────────────────────────────────────────────────────

@router.message(Command("developer"))
async def cmd_developer(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat administrator uchun.")
        return

    await message.answer(MENU_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")


# ── "Back to menu" callback (used by every sub-module) ───────────────────────

@router.callback_query(lambda c: c.data == DEV_MENU)
async def cb_back_to_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Clear any active AI FSM state when navigating back to the Developer main menu.

    Without this clear(), states such as AIChatStates.waiting_message would
    persist after the user leaves the AI sub-menu, causing subsequent messages
    to be routed to the wrong handler.
    """
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return

    await state.clear()
    await query.answer()
    await query.message.edit_text(
        MENU_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


# ── "Exit" callback ───────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == DEV_CLOSE)
async def cb_close(query: CallbackQuery) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Ruxsat yo'q.", show_alert=True)
        return

    await query.answer("Developer Mode yopildi.")
    await query.message.delete()
