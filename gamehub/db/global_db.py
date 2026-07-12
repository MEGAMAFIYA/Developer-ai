"""Global PostgreSQL database — stores game catalogue."""

import asyncpg
from config import config

_pool: asyncpg.Pool | None = None


async def get_global_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.GLOBAL_DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def close_global_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Games CRUD
# ---------------------------------------------------------------------------

async def add_game(name: str, display_name: str, description: str, url_path: str) -> dict:
    pool = await get_global_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO games (name, display_name, description, url_path)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (name) DO UPDATE
            SET display_name = EXCLUDED.display_name,
                description  = EXCLUDED.description,
                url_path     = EXCLUDED.url_path
        RETURNING *
        """,
        name, display_name, description, url_path,
    )
    return dict(row)


async def get_all_games() -> list[dict]:
    pool = await get_global_pool()
    rows = await pool.fetch("SELECT * FROM games ORDER BY created_at")
    return [dict(r) for r in rows]


async def get_game_by_name(name: str) -> dict | None:
    pool = await get_global_pool()
    row = await pool.fetchrow("SELECT * FROM games WHERE name = $1", name)
    return dict(row) if row else None
