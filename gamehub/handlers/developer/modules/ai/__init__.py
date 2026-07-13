"""AI Developer sub-package.

Maps to the user-facing "🤖 AI Developer" section inside Developer Mode.

Equivalent JS layout (for reference):
  index.js     → this file         (aggregates & exports router)
  menu.js      → menu.py           (keyboard builders + menu text)
  callbacks.js → callbacks.py      (all ai:* callback constants)
  states.js    → states.py         (FSM state groups)
  (handlers.py is Python-idiomatic extra — holds all handler functions)

To add a new AI feature:
  1. Add constant to callbacks.py
  2. Add FSM states to states.py   (if stateful)
  3. Add button to menu.py → ai_menu_keyboard()
  4. Add handler to handlers.py
  — no changes needed here unless you split into a new file
"""

from aiogram import Router

from handlers.developer.modules.ai import handlers
from handlers.developer.modules.ai import chat             # Phase 3 — live FSM features
from handlers.developer.modules.ai import key_manager      # Phase 4 — API key management
from handlers.developer.modules.ai import file_tools       # Phase 4 — File Manager
from handlers.developer.modules.ai import database_tools   # Phase 4 — Database Manager
from handlers.developer.modules.ai import github_tools     # Phase 4 — GitHub Manager
from handlers.developer.modules.ai import project_tools    # Phase 4 — Project Manager

# Single router exposed to developer/__init__.py
router = Router(name="dev:ai")
router.include_router(handlers.router)
router.include_router(chat.router)             # Phase 3
router.include_router(key_manager.router)      # Phase 4 — API key management
router.include_router(file_tools.router)       # Phase 4 — File Manager
router.include_router(database_tools.router)   # Phase 4 — Database Manager
router.include_router(github_tools.router)     # Phase 4 — GitHub Manager
router.include_router(project_tools.router)    # Phase 4 — Project Manager
