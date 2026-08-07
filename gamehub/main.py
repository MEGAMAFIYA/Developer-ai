"""Entry point — runs aiogram bot (polling) + FastAPI (uvicorn) concurrently.

Graceful shutdown
─────────────────
Both SIGTERM (sent by Render/Docker on deploy/scale-down) and SIGINT
(Ctrl-C in development) are handled:
  1. uvicorn is told to stop accepting new requests (server.should_exit).
  2. The bot polling task is cancelled and the bot session is closed.
  3. Both asyncpg connection pools are closed cleanly.
  4. The process exits with code 0.

Logging
───────
When RENDER=true (set by render.yaml) only stdout is used — Render
streams it to its log viewer.  In all other environments a rotating file
handler is added alongside stdout.
"""

import asyncio
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import init_databases, close_global_pool, close_game_pool
from bot.router import main_router
from bot.commands import register_commands
from api.app import app as fastapi_app

# ── Logging setup ─────────────────────────────────────────────────────────────
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

# File handler only in non-container environments
if not os.getenv("RENDER"):
    _LOG_DIR = Path(__file__).resolve().parent / "logs"
    _LOG_DIR.mkdir(exist_ok=True)
    _handlers.append(
        RotatingFileHandler(
            _LOG_DIR / "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    )

logging.basicConfig(level=logging.INFO, format=_LOG_FMT, handlers=_handlers)
logger = logging.getLogger(__name__)


# ── Bot and server builders ────────────────────────────────────────────────────

def _make_bot() -> Bot:
    return Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _make_server() -> uvicorn.Server:
    cfg = uvicorn.Config(
        app=fastapi_app,
        host=config.HOST,
        port=config.PORT,
        log_level="info",
        # Use uvicorn's built-in access log for production visibility
        access_log=True,
    )
    server = uvicorn.Server(cfg)
    # We handle signals ourselves — prevent uvicorn from installing its own
    server.install_signal_handlers = lambda: None
    return server


# ── Main coroutine ────────────────────────────────────────────────────────────

async def main() -> None:
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    bot_disabled = os.getenv("DISABLE_BOT", "").strip().lower() == "true"

    def _handle_signal() -> None:
        if not shutdown_event.is_set():
            logger.info("Shutdown signal received — beginning graceful shutdown.")
            shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    # ── Database init ─────────────────────────────────────────────────────────
    logger.info("Initialising databases...")
    await init_databases()
    logger.info("Databases ready.")

    # ── Build services ────────────────────────────────────────────────────────
    bot = None
    bot_task = None
    if bot_disabled:
        logger.info("[STARTUP] Telegram bot disabled on this environment.")
    else:
        bot = _make_bot()
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(main_router)
        await register_commands(bot)

    server = _make_server()
    logger.info("Starting FastAPI on %s:%s...", config.HOST, config.PORT)

    # ── Concurrent tasks ──────────────────────────────────────────────────────
    server_task = asyncio.create_task(server.serve(), name="uvicorn-server")
    if not bot_disabled:
        bot_task = asyncio.create_task(
            dp.start_polling(bot, allowed_updates=["message", "callback_query"]),
            name="bot-polling",
        )

    async def _shutdown_watcher() -> None:
        """Wait for shutdown signal then stop both services in order."""
        await shutdown_event.wait()
        logger.info("Stopping uvicorn...")
        server.should_exit = True

        if bot_task is not None and bot is not None:
            logger.info("Stopping bot polling...")
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass
            finally:
                await bot.session.close()
                logger.info("Bot session closed.")

    try:
        if not bot_disabled:
            logger.info("Starting bot polling...")
        tasks = [server_task, _shutdown_watcher()]
        if bot_task is not None:
            tasks.insert(1, bot_task)
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Unexpected error in main gather")
    finally:
        logger.info("Closing database pools...")
        for name, closer in [("global_db", close_global_pool), ("game_db", close_game_pool)]:
            try:
                await closer()
                logger.info("%s pool closed.", name)
            except Exception as exc:
                logger.warning("Error closing %s pool: %s", name, exc)
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass  # already handled via signal handlers above
