"""Diamond reward system — stub ready for future activation.

When DIAMONDS_ENABLED is set to True below, implement award logic here.
Every public function is a no-op while disabled, so it is safe to wire up now.

Planned reward model (adjust before enabling):
  • new personal record  : +10 diamonds
  • top-3 global rank    : +5  diamonds bonus
  • top-1 global rank    : +10 diamonds bonus
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flag — flip to True when ready to go live
# ---------------------------------------------------------------------------
DIAMONDS_ENABLED: bool = False


async def award_for_score(
    *,
    user_id: int,
    username: str,
    first_name: str,
    game_name: str,
    score: int,
    is_new_record: bool,
    rank: int,
) -> int:
    """Award diamonds for a submitted score.

    Returns diamonds earned (always 0 while DIAMONDS_ENABLED is False).
    """
    if not DIAMONDS_ENABLED:
        return 0

    earned = 0

    if is_new_record:
        earned += 10          # personal record bonus
    if rank == 1:
        earned += 10          # #1 global bonus
    elif rank <= 3:
        earned += 5           # top-3 bonus

    if earned > 0:
        await _add_diamonds(user_id, username, first_name, earned)
        logger.info(
            "diamonds: user=%s game=%s score=%s rank=%s earned=%s",
            user_id, game_name, score, rank, earned,
        )

    return earned


async def _add_diamonds(
    user_id: int,
    username: str,
    first_name: str,
    amount: int,
) -> None:
    """Upsert the diamonds balance table."""
    from database.game_db import get_game_pool
    pool = await get_game_pool()
    await pool.execute(
        """
        INSERT INTO diamonds (user_id, username, first_name, balance, total_earned)
        VALUES ($1, $2, $3, $4, $4)
        ON CONFLICT (user_id) DO UPDATE
            SET username     = EXCLUDED.username,
                first_name   = EXCLUDED.first_name,
                balance      = diamonds.balance + EXCLUDED.balance,
                total_earned = diamonds.total_earned + EXCLUDED.total_earned,
                updated_at   = NOW()
        """,
        user_id, username, first_name, amount,
    )


async def get_balance(user_id: int) -> int:
    """Return the user's current diamond balance (0 while disabled)."""
    if not DIAMONDS_ENABLED:
        return 0
    from database.game_db import get_game_pool
    pool = await get_game_pool()
    val = await pool.fetchval(
        "SELECT balance FROM diamonds WHERE user_id = $1", user_id,
    )
    return int(val) if val else 0
