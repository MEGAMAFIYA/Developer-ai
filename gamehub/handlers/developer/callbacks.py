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

DEV_PROJECT_MANAGER = "dev:pm"

# ── Log Manager sub-actions ───────────────────────────────────────────────────
DEV_LOG_VIEW     = "dev:log:view"
DEV_LOG_REFRESH  = "dev:log:refresh"
DEV_LOG_FILTER   = "dev:log:filter"
DEV_LOG_LVL_DBG  = "dev:log:lvl:dbg"
DEV_LOG_LVL_INF  = "dev:log:lvl:inf"
DEV_LOG_LVL_WRN  = "dev:log:lvl:wrn"
DEV_LOG_LVL_ERR  = "dev:log:lvl:err"
DEV_LOG_LVL_CRT  = "dev:log:lvl:crt"
DEV_LOG_SEARCH   = "dev:log:search"
DEV_LOG_DL_CUR   = "dev:log:dl:cur"
DEV_LOG_DL_ALL   = "dev:log:dl:all"
DEV_LOG_CLEAR    = "dev:log:clear"
DEV_LOG_CLEAR_OK = "dev:log:clear:ok"
DEV_LOG_DATE     = "dev:log:date"
DEV_LOG_AI       = "dev:log:ai"

# ── Project Manager sub-actions ───────────────────────────────────────────────
DEV_PM_INFO      = "dev:pm:info"
DEV_PM_STATS     = "dev:pm:stats"
DEV_PM_SEARCH    = "dev:pm:search"
DEV_PM_SRCH_NAME = "dev:pm:srch:name"
DEV_PM_SRCH_TEXT = "dev:pm:srch:text"
DEV_PM_MAINT     = "dev:pm:maint"
DEV_PM_PYCACHE   = "dev:pm:pycache"
DEV_PM_PYCACHE_OK= "dev:pm:pycache:ok"
DEV_PM_TEMP      = "dev:pm:temp"
DEV_PM_TEMP_OK   = "dev:pm:temp:ok"
DEV_PM_DISK      = "dev:pm:disk"
DEV_PM_EXPORT    = "dev:pm:export"
DEV_PM_EXPORT_OK = "dev:pm:export:ok"

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
    DEV_PROJECT_MANAGER,
)
