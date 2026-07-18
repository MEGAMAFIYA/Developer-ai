"""Global PostgreSQL database — dynamic game catalogue."""

import logging

import asyncpg
from config import config

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_global_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            config.GLOBAL_DATABASE_URL,
            min_size=1,
            max_size=5,
            # Recycle idle connections before Neon's 5-minute idle timeout
            max_inactive_connection_lifetime=300,
            # Hard cap on any single query (prevents hung connections)
            command_timeout=30,
            server_settings={"application_name": "kichik_oyinlar_global"},
        )
    return _pool


async def close_global_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def ping() -> bool:
    """Return True if the pool is reachable (used by /health endpoint)."""
    try:
        pool = await get_global_pool()
        await pool.fetchval("SELECT 1", timeout=2)
        return True
    except Exception as exc:
        logger.warning("global_db ping failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def add_game(
    slug: str,
    name: str,
    description: str,
    html_file: str,
    category: str = "arcade",
    image_url: str = "",
    active: bool = True,
) -> dict:
    pool = await get_global_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO games (slug, name, description, image_url, html_file, category, active)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (slug) DO UPDATE
            SET name        = EXCLUDED.name,
                description = EXCLUDED.description,
                image_url   = EXCLUDED.image_url,
                html_file   = EXCLUDED.html_file,
                category    = EXCLUDED.category,
                active      = EXCLUDED.active
        RETURNING *
        """,
        slug, name, description, image_url, html_file, category, active,
    )
    return dict(row)


async def get_all_games(only_active: bool = True) -> list[dict]:
    pool = await get_global_pool()
    if only_active:
        rows = await pool.fetch(
            "SELECT * FROM games WHERE active = TRUE ORDER BY created_at"
        )
    else:
        rows = await pool.fetch("SELECT * FROM games ORDER BY created_at")
    return [dict(r) for r in rows]


async def get_game_by_slug(slug: str) -> dict | None:
    pool = await get_global_pool()
    row = await pool.fetchrow("SELECT * FROM games WHERE slug = $1", slug)
    return dict(row) if row else None


async def ensure_game_exists(slug: str) -> None:
    """Auto-register a minimal game catalog entry when a new slug is first seen.

    Called by the score API before saving a score so that any game that submits
    a score automatically appears in /reyting without manual backend changes.
    Existing entries are never overwritten.
    """
    pool = await get_global_pool()
    await pool.execute(
        """
        INSERT INTO games (slug, name, description, html_file, category, active)
        VALUES ($1, $1, '', $1 || '.html', 'arcade', TRUE)
        ON CONFLICT (slug) DO NOTHING
        """,
        slug,
    )


async def update_game_image(slug: str, image_url: str) -> None:
    pool = await get_global_pool()
    await pool.execute(
        "UPDATE games SET image_url = $1 WHERE slug = $2", image_url, slug
    )


# ---------------------------------------------------------------------------
# Settings (key-value store for admin configuration)
# ---------------------------------------------------------------------------

async def get_setting(key: str) -> str | None:
    pool = await get_global_pool()
    row = await pool.fetchrow("SELECT value FROM settings WHERE key = $1", key)
    return row["value"] if row else None


async def set_setting(key: str, value: str) -> None:
    pool = await get_global_pool()
    await pool.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = NOW()
        """,
        key, value,
    )


async def delete_setting(key: str) -> None:
    pool = await get_global_pool()
    await pool.execute("DELETE FROM settings WHERE key = $1", key)


async def update_game(
    slug: str,
    name: str,
    description: str,
    image_url: str,
    html_file: str,
    category: str,
    tags: str,
    active: bool,
) -> dict:
    """Update all editable fields of a game. Slug and ID are never changed."""
    pool = await get_global_pool()
    row = await pool.fetchrow(
        """
        UPDATE games
        SET name        = $2,
            description = $3,
            image_url   = $4,
            html_file   = $5,
            category    = $6,
            tags        = $7,
            active      = $8
        WHERE slug = $1
        RETURNING *
        """,
        slug, name, description, image_url, html_file, category, tags, active,
    )
    return dict(row) if row else {}
