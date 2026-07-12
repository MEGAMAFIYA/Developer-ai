"""Combine all handlers into one aiogram router."""

from aiogram import Router
from handlers import start, admin, edit, rating, games

main_router = Router()
main_router.include_router(start.router)
main_router.include_router(admin.router)
main_router.include_router(edit.router)
main_router.include_router(rating.router)
main_router.include_router(games.router)
