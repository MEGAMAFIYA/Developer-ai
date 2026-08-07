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


async def delete_game_by_html_file(html_file: str) -> list[dict]:
    """Hard-delete every game record whose html_file matches.

    Returns the list of deleted rows (each as a dict) so the caller can
    inspect image_url and clean up orphaned local assets.  Called by the
    Files module when a game HTML file is removed from disk.
    """
    pool = await get_global_pool()
    rows = await pool.fetch(
        "DELETE FROM games WHERE html_file = $1 RETURNING *",
        html_file,
    )
    return [dict(r) for r in rows]


async def is_image_url_shared(image_url: str) -> bool:
    """Return True if at least one game record still references this image_url.

    Used after deleting a game to decide whether its local image asset can
    be safely removed without breaking another game's card.
    """
    if not image_url:
        return False
    pool = await get_global_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM games WHERE image_url = $1",
        image_url,
    )
    return (count or 0) > 0


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
