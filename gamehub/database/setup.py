"""Create/migrate tables and seed initial data."""

import logging
from database.global_db import get_global_pool, add_game
from database.game_db import get_game_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

GLOBAL_SCHEMA = """
-- Drop old schema if it exists (column 'slug' signals new schema)
DO $$
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
$$;

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
);
"""

GAME_SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    username   VARCHAR(128) NOT NULL DEFAULT '',
    first_name VARCHAR(128) NOT NULL DEFAULT '',
    game_name  VARCHAR(64) NOT NULL,
    score      INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scores_game_name ON scores (game_name);
CREATE INDEX IF NOT EXISTS idx_scores_user_id   ON scores (user_id);
"""

# ---------------------------------------------------------------------------
# Seed data — only applied on first run (ON CONFLICT DO UPDATE)
# ---------------------------------------------------------------------------

INITIAL_GAMES = [
    {
        "slug": "snake",
        "name": "🐍 Ilon O'yini",
        "description": "Klassik ilon o'yini. Ovqat ye, o'sib bor!",
        "html_file": "snake.html",
        "category": "arcade",
        "image_url": "",
    },
    {
        "slug": "zombi",
        "name": "🧟 Zombi Omon Qolish",
        "description": "Zombilardan omon qol va yashab qol!",
        "html_file": "zombi.html",
        "category": "arcade",
        "image_url": "",
    },
]


async def init_databases() -> None:
    """Create all tables and seed initial games."""
    global_pool = await get_global_pool()
    async with global_pool.acquire() as conn:
        await conn.execute(GLOBAL_SCHEMA)
    logger.info("Global DB schema ready.")

    game_pool = await get_game_pool()
    async with game_pool.acquire() as conn:
        await conn.execute(GAME_SCHEMA)
    logger.info("Game DB schema ready.")

    for game in INITIAL_GAMES:
        await add_game(**game)
    logger.info("Initial games seeded.")
