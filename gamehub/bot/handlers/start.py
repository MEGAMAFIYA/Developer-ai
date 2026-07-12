from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name or "O'yinchi"
    await message.answer(
        f"👋 Salom, <b>{name}</b>!\n\n"
        "🎮 <b>Mini O'yinlar Botiga xush kelibsiz!</b>\n\n"
        "📋 Mavjud buyruqlar:\n"
        "  /oyinlar — barcha o'yinlar ro'yxati\n"
        "  /oyinlar &lt;nom&gt; — o'yinni boshlash\n\n"
        "🕹 O'ynashni boshlang!",
        parse_mode="HTML",
    )
