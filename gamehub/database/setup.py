"""Create/migrate tables and seed initial data."""

import logging
from database.global_db import get_global_pool, add_game
from database.game_db import get_game_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema statements — each is a single SQL command so asyncpg can execute
# them individually without choking on multi-statement strings.
# ---------------------------------------------------------------------------

# 1. Drop old table if it pre-dates the slug column (legacy migration)
_DROP_LEGACY = """
DO $tag$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'games'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'games' AND column_name = 'slug'
    ) THEN
        DROP TABLE games;
    END IF;
END;
$tag$
"""

# 2. Create the games table
_CREATE_GAMES = """
CREATE TABLE IF NOT EXISTS games (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(64) UNIQUE NOT NULL,
    name        VARCHAR(128) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_url   VARCHAR(512) NOT NULL DEFAULT '',
    html_file   VARCHAR(256) NOT NULL,
    category    VARCHAR(64) NOT NULL DEFAULT 'arcade',
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# 3. Add tags column if missing (non-destructive — safe to run every startup)
_ADD_TAGS_COLUMN = """
ALTER TABLE games ADD COLUMN IF NOT EXISTS tags TEXT NOT NULL DEFAULT ''
"""

# ---------------------------------------------------------------------------
# Scores table
# ---------------------------------------------------------------------------

_CREATE_SCORES = """
CREATE TABLE IF NOT EXISTS scores (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    username   VARCHAR(128) NOT NULL DEFAULT '',
    first_name VARCHAR(128) NOT NULL DEFAULT '',
    game_name  VARCHAR(64) NOT NULL,
    score      INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_IDX_GAME_NAME = "CREATE INDEX IF NOT EXISTS idx_scores_game_name ON scores (game_name)"
_IDX_USER_ID   = "CREATE INDEX IF NOT EXISTS idx_scores_user_id   ON scores (user_id)"

# Non-destructive score-table migrations (safe on every startup)
_ADD_SCORES_CHAT_ID = """
ALTER TABLE scores ADD COLUMN IF NOT EXISTS chat_id BIGINT NOT NULL DEFAULT 0
"""
_ADD_SCORES_CHAT_TITLE = """
ALTER TABLE scores ADD COLUMN IF NOT EXISTS chat_title VARCHAR(128) NOT NULL DEFAULT ''
"""
_IDX_CHAT_ID = "CREATE INDEX IF NOT EXISTS idx_scores_chat_id ON scores (chat_id)"

# Unique constraint required for the ON CONFLICT UPSERT in save_score().
# Without this index the UPSERT would fail at runtime (PostgreSQL requires a
# unique constraint or unique index matching the ON CONFLICT column list).
# CREATE UNIQUE INDEX IF NOT EXISTS is safe to run on every startup.
_UIDX_SCORES_UPSERT = """
CREATE UNIQUE INDEX IF NOT EXISTS uidx_scores_user_game_chat
    ON scores (user_id, game_name, chat_id)
"""

# Settings — generic key/value store for admin configuration (AI key, etc.)
_CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key        VARCHAR(128) PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# Diamond reward system — disabled until services/diamond_service.py is enabled
_CREATE_DIAMONDS = """
CREATE TABLE IF NOT EXISTS diamonds (
    id           SERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL UNIQUE,
    username     VARCHAR(128) NOT NULL DEFAULT '',
    first_name   VARCHAR(128) NOT NULL DEFAULT '',
    balance      INTEGER NOT NULL DEFAULT 0,
    total_earned INTEGER NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# ---------------------------------------------------------------------------
# Seed data — ON CONFLICT DO UPDATE keeps re-runs idempotent
# ---------------------------------------------------------------------------

# All initial games have been removed. New games are uploaded via Developer → Files.
INITIAL_GAMES: list[dict] = []


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

async def init_databases() -> None:
    """Create / migrate all tables and seed initial games."""
    global_pool = await get_global_pool()
    async with global_pool.acquire() as conn:
        await conn.execute(_DROP_LEGACY)
        await conn.execute(_CREATE_GAMES)
        await conn.execute(_ADD_TAGS_COLUMN)
        await conn.execute(_CREATE_SETTINGS)
    logger.info("Global DB schema ready.")

    game_pool = await get_game_pool()
    async with game_pool.acquire() as conn:
        await conn.execute(_CREATE_SCORES)
        await conn.execute(_IDX_GAME_NAME)
        await conn.execute(_IDX_USER_ID)
        # Non-destructive migrations
        await conn.execute(_ADD_SCORES_CHAT_ID)
        await conn.execute(_ADD_SCORES_CHAT_TITLE)
        await conn.execute(_IDX_CHAT_ID)
        # Unique index required by the ON CONFLICT UPSERT in save_score()
        await conn.execute(_UIDX_SCORES_UPSERT)
        # Diamond reward system (disabled until DIAMONDS_ENABLED = True)
        await conn.execute(_CREATE_DIAMONDS)
    logger.info("Game DB schema ready.")

    for game in INITIAL_GAMES:
        await add_game(**game)
    logger.info("Initial games seeded.")

    # Load persisted AI settings into the live manager singleton
    await _load_ai_settings()


async def _load_ai_settings() -> None:
    """Load AI settings with priority: DB (1st) → env vars (2nd) → provider defaults (3rd).

    DB values set via Telegram always win over .env / config.py defaults.
    If DB has no value for a given key, the env-var fallback is used.
    Provider-level defaults (_DEFAULT_MODEL etc.) are handled inside the provider classes.
    """
    import config as cfg
    from database.global_db import get_setting

    db_provider = await get_setting("ai_provider")
    db_api_key  = await get_setting("ai_api_key")
    db_model    = await get_setting("ai_model")

    # Priority 1 = DB, Priority 2 = env var
    provider = db_provider or cfg.config.AI_PROVIDER or ""
    api_key  = db_api_key  or cfg.config.AI_API_KEY  or ""
    model    = db_model    or cfg.config.AI_MODEL    or ""

    if provider or api_key:
        from handlers.developer.modules.ai import services
        services.reload_manager(provider=provider, api_key=api_key, model=model)
        logger.info(
            "AI settings loaded: provider=%s key_set=%s model=%s "
            "(db_provider=%s db_key=%s db_model=%s)",
            provider or "none", bool(api_key), model or "none",
            bool(db_provider), bool(db_api_key), bool(db_model),
        )
