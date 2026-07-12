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
        "  /oyinlar — barcha o'yinlar\n"
        "  /oyinlar &lt;slug&gt; — bitta o'yin kartochkasi\n\n"
        "🕹 O'ynashni boshlang!",
        parse_mode="HTML",
    )
