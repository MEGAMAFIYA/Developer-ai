"""Game PostgreSQL database — player scores and leaderboards."""

import logging

import asyncpg
from config import config

logger = logging.getLogger(__name__)

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
# Score persistence
# ---------------------------------------------------------------------------

async def save_score(
    user_id: int,
    username: str,
    first_name: str,
    game_name: str,
    score: int,
    chat_id: int = 0,
    chat_title: str = "",
) -> dict:
    """Persist a score only when it beats the user's personal best.

    Returns a dict with:
      row           – the inserted asyncpg Record as dict, or None if not saved
      is_new_record – True if this score beats the user's previous best
      previous_best – the user's best score before this call (0 if first time)
      rank          – global position of the user's best score (1-based)
    """
    pool = await get_game_pool()
    logger.info(
        "Score received: user=%s game=%s score=%s chat=%s",
        user_id, game_name, score, chat_id,
    )

    async with pool.acquire() as conn:
        # ── 1. Capture previous personal best ──────────────────────────────
        prev: int | None = await conn.fetchval(
            "SELECT MAX(score) FROM scores WHERE user_id = $1 AND game_name = $2",
            user_id, game_name,
        )
        previous_best: int = prev if prev is not None else 0
        is_new_record: bool = (prev is None) or (score > previous_best)

        # ── 2. Only write to DB when score is a personal best ───────────────
        if not is_new_record:
            logger.info(
                "Score rejected (not a new best): user=%s game=%s score=%s prev_best=%s",
                user_id, game_name, score, previous_best,
            )
            # Return rank of the user's current best (not this score)
            rank_val: int = await conn.fetchval(
                """
                SELECT COUNT(*) + 1
                FROM (
                    SELECT user_id, MAX(score) AS best
                    FROM scores
                    WHERE game_name = $1
                    GROUP BY user_id
                ) sub
                WHERE sub.best > $2
                """,
                game_name, previous_best,
            ) or 1
            return {
                "row":           None,
                "is_new_record": False,
                "previous_best": previous_best,
                "rank":          int(rank_val),
            }

        row = await conn.fetchrow(
            """
            INSERT INTO scores
                (user_id, username, first_name, game_name, score, chat_id, chat_title)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            user_id, username, first_name, game_name, score, chat_id, chat_title,
        )
        logger.info(
            "Score accepted (new best): user=%s game=%s score=%s prev_best=%s row_id=%s",
            user_id, game_name, score, previous_best, row["id"],
        )

        # ── 3. Global rank of this new best ────────────────────────────────
        rank_val = await conn.fetchval(
            """
            SELECT COUNT(*) + 1
            FROM (
                SELECT user_id, MAX(score) AS best
                FROM scores
                WHERE game_name = $1
                GROUP BY user_id
            ) sub
            WHERE sub.best > $2
            """,
            game_name, score,
        ) or 1

        logger.info(
            "Ranking updated: user=%s game=%s rank=%s",
            user_id, game_name, rank_val,
        )

    return {
        "row":           dict(row),
        "is_new_record": True,
        "previous_best": previous_best,
        "rank":          int(rank_val),
    }


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------

async def get_global_leaderboard(game_name: str, limit: int = 20) -> list[dict]:
    """Best score per player, all groups combined, ordered best-first."""
    pool = await get_game_pool()
    rows = await pool.fetch(
        """
        SELECT user_id, username, first_name, MAX(score) AS best_score
        FROM scores
        WHERE game_name = $1
        GROUP BY user_id, username, first_name
        ORDER BY best_score DESC
        LIMIT $2
        """,
        game_name, limit,
    )
    return [dict(r) for r in rows]


async def get_group_leaderboard(
    game_name: str, chat_id: int, limit: int = 20
) -> list[dict]:
    """Best score per player, restricted to a single Telegram group."""
    pool = await get_game_pool()
    rows = await pool.fetch(
        """
        SELECT user_id, username, first_name, MAX(score) AS best_score
        FROM scores
        WHERE game_name = $1 AND chat_id = $2
        GROUP BY user_id, username, first_name
        ORDER BY best_score DESC
        LIMIT $3
        """,
        game_name, chat_id, limit,
    )
    return [dict(r) for r in rows]


async def get_global_player_count(game_name: str) -> int:
    pool = await get_game_pool()
    val = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM scores WHERE game_name = $1",
        game_name,
    )
    return int(val) if val else 0


async def get_group_player_count(game_name: str, chat_id: int) -> int:
    pool = await get_game_pool()
    val = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM scores WHERE game_name = $1 AND chat_id = $2",
        game_name, chat_id,
    )
    return int(val) if val else 0


# ---------------------------------------------------------------------------
# Per-user helpers
# ---------------------------------------------------------------------------

async def get_user_best(user_id: int, game_name: str) -> dict | None:
    """Return the row with the user's highest score for compatibility."""
    pool = await get_game_pool()
    row = await pool.fetchrow(
        "SELECT * FROM scores WHERE user_id=$1 AND game_name=$2 ORDER BY score DESC LIMIT 1",
        user_id, game_name,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Legacy helper kept for backwards compatibility
# ---------------------------------------------------------------------------

async def get_top_scores(game_name: str, limit: int = 10) -> list[dict]:
    """Top N scores (one per user).  Use get_global_leaderboard for new code."""
    return await get_global_leaderboard(game_name, limit)
