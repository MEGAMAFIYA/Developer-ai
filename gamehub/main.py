"""Entry point — runs aiogram bot (polling) + FastAPI (uvicorn) concurrently."""

import asyncio
import logging
import sys

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import init_databases, close_global_pool, close_game_pool
from bot.router import main_router
from api.app import app as fastapi_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def start_bot() -> None:
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(main_router)

    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


async def start_server() -> None:
    server_config = uvicorn.Config(
        app=fastapi_app,
        host=config.HOST,
        port=config.PORT,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    logger.info("Starting FastAPI on %s:%s...", config.HOST, config.PORT)
    await server.serve()


async def main() -> None:
    logger.info("Initialising databases...")
    await init_databases()
    logger.info("Databases ready.")

    try:
        await asyncio.gather(start_bot(), start_server())
    finally:
        try:
            await close_global_pool()
        except Exception:
            pass
        try:
            await close_game_pool()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")
