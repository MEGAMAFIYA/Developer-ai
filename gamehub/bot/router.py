"""Combine all bot routers into one."""

from aiogram import Router
from bot.handlers import start, admin, games

main_router = Router()
main_router.include_router(start.router)
main_router.include_router(admin.router)
main_router.include_router(games.router)
