"""Developer Mode handler package.

This package aggregates all sub-routers so the rest of the bot only needs:

    from handlers.developer import router as developer_router
    main_router.include_router(developer_router)

To add a new module:
  1. Create  handlers/developer/modules/<name>.py  with a `router` and callbacks.
  2. Add its callback constant(s) to  handlers/developer/callbacks.py
  3. Add a keyboard button to  handlers/developer/keyboards.py
  4. Import and include the router in the list below — done.
"""

from aiogram import Router

from handlers.developer import menu
from handlers.developer.modules import (
    games, ai, commands, files,
    database, stats, github, settings,
    test, logs, backup, project_manager,
)

# The top-level router for the entire Developer Mode feature.
# Included once into bot/router.py — zero impact on other handlers.
router = Router(name="developer")

# Core navigation (command + back + close)
router.include_router(menu.router)

# Individual feature modules — add new ones here
router.include_router(games.router)
router.include_router(ai.router)
router.include_router(commands.router)
router.include_router(files.router)
router.include_router(database.router)
router.include_router(stats.router)
router.include_router(github.router)
router.include_router(settings.router)
router.include_router(test.router)
router.include_router(logs.router)
router.include_router(backup.router)
router.include_router(project_manager.router)
