"""Game PostgreSQL database — player scores."""

import asyncpg
from config import config

_pool: asyncpg.Pool | None = None


async def get_game_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.GAME_DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def close_game_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Scores CRUD
# ---------------------------------------------------------------------------

async def save_score(
    user_id: int,
    username: str,
    first_name: str,
    game_name: str,
    score: int,
) -> dict:
    pool = await get_game_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO scores (user_id, username, first_name, game_name, score)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        user_id, username, first_name, game_name, score,
    )
    return dict(row)


async def get_top_scores(game_name: str, limit: int = 10) -> list[dict]:
    pool = await get_game_pool()
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (user_id)
            user_id, username, first_name, game_name, score, created_at
        FROM scores
        WHERE game_name = $1
        ORDER BY user_id, score DESC
        """,
        game_name,
    )
    top = sorted(rows, key=lambda r: r["score"], reverse=True)[:limit]
    return [dict(r) for r in top]


async def get_user_best(user_id: int, game_name: str) -> dict | None:
    pool = await get_game_pool()
    row = await pool.fetchrow(
        "SELECT * FROM scores WHERE user_id=$1 AND game_name=$2 ORDER BY score DESC LIMIT 1",
        user_id, game_name,
    )
    return dict(row) if row else None
