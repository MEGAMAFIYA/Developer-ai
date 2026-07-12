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

# ---------------------------------------------------------------------------
# Seed data — ON CONFLICT DO UPDATE keeps re-runs idempotent
# ---------------------------------------------------------------------------

INITIAL_GAMES = [
    {
        "slug":        "snake",
        "name":        "🐍 Ilon O'yini",
        "description": "Klassik ilon o'yini. Ovqat ye, o'sib bor!",
        "html_file":   "snake.html",
        "category":    "arcade",
        "image_url":   "",
    },
    {
        "slug":        "zombi",
        "name":        "🧟 Zombi Omon Qolish",
        "description": "Zombilardan omon qol va yashab qol!",
        "html_file":   "zombi.html",
        "category":    "arcade",
        "image_url":   "",
    },
]


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
    logger.info("Global DB schema ready.")

    game_pool = await get_game_pool()
    async with game_pool.acquire() as conn:
        await conn.execute(_CREATE_SCORES)
        await conn.execute(_IDX_GAME_NAME)
        await conn.execute(_IDX_USER_ID)
    logger.info("Game DB schema ready.")

    for game in INITIAL_GAMES:
        await add_game(**game)
    logger.info("Initial games seeded.")
