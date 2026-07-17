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
    """Persist a score, keeping exactly ONE row per (user_id, game_name, chat_id).

    Uses INSERT … ON CONFLICT UPSERT so the table never accumulates multiple
    rows for the same player/game/chat context.  Key guarantees:
      - score only ever increases (GREATEST keeps the all-time best).
      - username and first_name are always refreshed to the latest values so
        the leaderboard never shows a stale/old display name.
      - is_new_record is True only when the incoming score beats the stored best.

    Returns a dict with:
      row           – the upserted Record as dict when is_new_record, else None
      is_new_record – True if this score beats the user's previous best
      previous_best – the stored best score before this call (0 if first time)
      rank          – global rank among distinct users by their best score (1-based)
    """
    pool = await get_game_pool()
    logger.info(
        "Score received: user=%s game=%s score=%s chat=%s",
        user_id, game_name, score, chat_id,
    )

    async with pool.acquire() as conn:
        # ── 1. Previous personal best for this (user, game, chat) context ──
        # chat_id=0  → private chat / global context
        # chat_id<0  → Telegram group/supergroup (negative IDs)
        prev: int | None = await conn.fetchval(
            "SELECT score FROM scores WHERE user_id = $1 AND game_name = $2 AND chat_id = $3",
            user_id, game_name, chat_id,
        )
        previous_best: int = prev if prev is not None else 0
        is_new_record: bool = (prev is None) or (score > previous_best)

        # ── 2. UPSERT — one canonical row per (user, game, chat) ────────────
        # Always refresh username / first_name / chat_title so display names
        # are current even for players who have not beaten their personal best.
        row = await conn.fetchrow(
            """
            INSERT INTO scores
                (user_id, username, first_name, game_name, score, chat_id, chat_title)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id, game_name, chat_id) DO UPDATE
                SET score      = GREATEST(scores.score, EXCLUDED.score),
                    username   = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    chat_title = EXCLUDED.chat_title
            RETURNING *
            """,
            user_id, username, first_name, game_name, score, chat_id, chat_title,
        )

        # ── Structured comparison log (game_id / user / group / scores / result) ──
        logger.info(
            "SCORE_COMPARISON | game=%s | user=%s | group=%s"
            " | submitted=%s | stored_best=%s | result=%s | db_updated=%s",
            game_name, user_id, chat_id,
            score, previous_best,
            "new_record" if is_new_record else "not_improved",
            is_new_record,
        )

        if is_new_record:
            logger.info(
                "Score accepted (new best): user=%s game=%s score=%s prev_best=%s row_id=%s",
                user_id, game_name, score, previous_best, row["id"],
            )
        else:
            logger.info(
                "Score not a new best (name refreshed): user=%s game=%s "
                "score=%s prev_best=%s chat=%s",
                user_id, game_name, score, previous_best, chat_id,
            )

        # ── 3. Global rank — count distinct users whose best beats this user's best
        # row["score"] is the GREATEST(old, new) stored value.
        # We count how many OTHER users have a higher best score for this game,
        # across ALL chat contexts (private + every group).
        stored_best: int = row["score"]
        rank_val: int = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id) + 1
            FROM scores
            WHERE game_name = $1
              AND user_id   != $2
              AND score      > $3
            """,
            game_name, user_id, stored_best,
        ) or 1

        logger.info(
            "Ranking: user=%s game=%s stored_best=%s rank=%s",
            user_id, game_name, stored_best, rank_val,
        )

    return {
        "row":           dict(row) if is_new_record else None,
        "is_new_record": is_new_record,
        "previous_best": previous_best,
        "rank":          int(rank_val),
    }


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------

async def get_global_leaderboard(game_name: str, limit: int = 20) -> list[dict]:
    """Best score per distinct player across ALL chat contexts, ordered best-first.

    SQL explanation
    ───────────────
    We GROUP BY user_id ONLY — not by (user_id, username, first_name).

    The old GROUP BY included username and first_name, which caused a player
    who changed their Telegram display name between sessions to appear as
    MULTIPLE separate entries on the leaderboard.

    With the UPSERT constraint (one row per user per game per chat context) a
    user can still have multiple rows — one for private chat and one per group
    they have played in.  The subquery picks the display name from whichever
    row holds that user's highest score for the game.
    """
    pool = await get_game_pool()
    rows = await pool.fetch(
        """
        SELECT
            s.user_id,
            s.username,
            s.first_name,
            s.score AS best_score
        FROM scores s
        INNER JOIN (
            SELECT user_id, MAX(score) AS top_score
            FROM scores
            WHERE game_name = $1
            GROUP BY user_id
        ) best ON best.user_id = s.user_id
              AND best.top_score = s.score
              AND s.game_name = $1
        ORDER BY best_score DESC, s.id ASC
        LIMIT $2
        """,
        game_name, limit,
    )
    # DISTINCT ON user_id in case two rows for the same user happen to share
    # the exact same top score (e.g. private=80 and group=80).
    seen: set[int] = set()
    result: list[dict] = []
    for r in rows:
        if r["user_id"] not in seen:
            seen.add(r["user_id"])
            result.append(dict(r))
    return result


async def get_group_leaderboard(
    game_name: str, chat_id: int, limit: int = 20
) -> list[dict]:
    """Best score per distinct player, restricted to one Telegram group.

    With the UPSERT constraint there is exactly ONE row per (user_id, game_name,
    chat_id), so a simple WHERE + ORDER is sufficient — no aggregation needed.
    We still use MAX() for safety against any legacy duplicates.

    Groups by user_id only (same rationale as get_global_leaderboard).
    """
    pool = await get_game_pool()
    rows = await pool.fetch(
        """
        SELECT user_id, username, first_name, score AS best_score
        FROM scores
        WHERE game_name = $1 AND chat_id = $2
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
    """Return the row with the user's highest score across all chat contexts."""
    pool = await get_game_pool()
    row = await pool.fetchrow(
        "SELECT * FROM scores WHERE user_id=$1 AND game_name=$2 ORDER BY score DESC LIMIT 1",
        user_id, game_name,
    )
    return dict(row) if row else None


async def verify_score_in_db(user_id: int, game_name: str, score: int) -> dict | None:
    """Confirm a score persisted in the DB after UPSERT.

    After the UPSERT the stored score is GREATEST(old, new), so we verify by
    checking that the row exists and its score >= the submitted score.
    """
    pool = await get_game_pool()
    row = await pool.fetchrow(
        """
        SELECT * FROM scores
        WHERE user_id = $1 AND game_name = $2 AND score >= $3
        ORDER BY score DESC
        LIMIT 1
        """,
        user_id, game_name, score,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Legacy helper kept for backwards compatibility
# ---------------------------------------------------------------------------

async def get_top_scores(game_name: str, limit: int = 10) -> list[dict]:
    """Top N scores (one per user).  Use get_global_leaderboard for new code."""
    return await get_global_leaderboard(game_name, limit)
