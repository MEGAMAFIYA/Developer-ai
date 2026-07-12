"""Create tables and seed initial data."""

import logging
from db.global_db import get_global_pool, add_game
from db.game_db import get_game_pool

logger = logging.getLogger(__name__)

GLOBAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(64) UNIQUE NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    url_path     VARCHAR(256) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

INITIAL_GAMES = [
    {
        "name": "snake",
        "display_name": "🐍 Ilon O'yini",
        "description": "Klassik ilon o'yini. Ovqat ye, o'sib bor!",
        "url_path": "/webapp/games/ilon.html",
    },
    {
        "name": "zombi",
        "display_name": "🧟 Zombi Omon Qolish",
        "description": "Zombilardan omon qol va yashab qol!",
        "url_path": "/webapp/games/zombi.html",
    },
]


async def init_databases() -> None:
    """Create all tables and seed initial games."""
    # Global DB
    global_pool = await get_global_pool()
    async with global_pool.acquire() as conn:
        await conn.execute(GLOBAL_SCHEMA)
    logger.info("Global DB schema ready.")

    # Game DB
    game_pool = await get_game_pool()
    async with game_pool.acquire() as conn:
        await conn.execute(GAME_SCHEMA)
    logger.info("Game DB schema ready.")

    # Seed initial games
    for game in INITIAL_GAMES:
        await add_game(**game)
    logger.info("Initial games seeded.")
