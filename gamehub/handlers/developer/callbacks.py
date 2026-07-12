"""Developer Mode — all callback data constants.

Naming convention:  dev:<module>:<action>
  - dev:menu        → back to main developer menu
  - dev:close       → close / exit developer mode
  - dev:<module>    → open a specific module

When a module grows sub-actions, extend it here:
  e.g.  DEV_GAMES_LIST   = "dev:games:list"
        DEV_GAMES_ADD    = "dev:games:add"
"""

# ── Main menu navigation ─────────────────────────────────────────────────────
DEV_MENU  = "dev:menu"   # back-to-menu button used by every sub-module
DEV_CLOSE = "dev:close"  # ❌ Chiqish — deletes the menu message

# ── Module entry points ──────────────────────────────────────────────────────
DEV_GAMES    = "dev:games"
DEV_AI       = "dev:ai"
DEV_COMMANDS = "dev:commands"
DEV_FILES    = "dev:files"
DEV_DATABASE = "dev:database"
DEV_STATS    = "dev:stats"
DEV_GITHUB   = "dev:github"
DEV_SETTINGS = "dev:settings"
DEV_TEST     = "dev:test"
DEV_LOGS     = "dev:logs"
DEV_BACKUP   = "dev:backup"

# ── Flat list — useful for programmatic access (e.g. tests, middleware) ───────
ALL_MODULE_CALLBACKS = (
    DEV_GAMES,
    DEV_AI,
    DEV_COMMANDS,
    DEV_FILES,
    DEV_DATABASE,
    DEV_STATS,
    DEV_GITHUB,
    DEV_SETTINGS,
    DEV_TEST,
    DEV_LOGS,
    DEV_BACKUP,
)
