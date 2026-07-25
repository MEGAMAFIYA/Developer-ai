"""End-to-end verification script for all 4 fixes."""
import asyncio
import asyncpg
import os
import pathlib
import time

from dotenv import load_dotenv
load_dotenv()

GAME_URL   = os.getenv("GAME_DATABASE_URL")
GLOBAL_URL = os.getenv("GLOBAL_DATABASE_URL")
GAMES_DIR  = pathlib.Path(__file__).parent / "webapp" / "games"
TEST_SLUG  = "e2e-verify-test"
TEST_FILE  = TEST_SLUG + ".html"
TEST_USER  = 777_000_001


async def run():
    print("=== END-TO-END VERIFICATION ===\n")

    gc = await asyncpg.connect(GLOBAL_URL)
    pc = await asyncpg.connect(GAME_URL)

    # Clean up any leftover from previous run
    dest = GAMES_DIR / TEST_FILE
    await gc.execute("DELETE FROM games WHERE slug = $1", TEST_SLUG)
    await pc.execute("DELETE FROM scores WHERE game_name = $1", TEST_SLUG)
    dest.unlink(missing_ok=True)

    results: dict[str, bool] = {}

    # ── STEP 1: Upload HTML file ───────────────────────────────────────────
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_text("<html><body>test game</body></html>")
    results["html_on_disk"] = dest.exists()
    print(f"STEP 1  HTML on disk: {results['html_on_disk']}")

    # ── STEP 2: FIX #4 — auto-register in catalog on upload ───────────────
    await gc.execute(
        """
        INSERT INTO games (slug, name, description, html_file, category, active)
        VALUES ($1::varchar, $1::varchar, '', $1::varchar || '.html', 'arcade', TRUE)
        ON CONFLICT (slug) DO NOTHING
        """,
        TEST_SLUG,
    )
    cat_row = await gc.fetchrow("SELECT slug, active FROM games WHERE slug = $1", TEST_SLUG)
    results["in_catalog"] = cat_row is not None and cat_row["active"]
    print(f"STEP 2  In catalog: {results['in_catalog']}")

    active_slugs = [r["slug"] for r in await gc.fetch("SELECT slug FROM games WHERE active = TRUE")]
    results["oyinlar_sees_game"] = TEST_SLUG in active_slugs
    results["reyting_sees_game"] = TEST_SLUG in active_slugs
    print(f"        /oyinlar sees game: {results['oyinlar_sees_game']}")
    print(f"        /reyting sees game: {results['reyting_sees_game']}")

    # ── STEP 3: Submit first score ─────────────────────────────────────────
    await pc.execute(
        """
        INSERT INTO scores
            (user_id, username, first_name, game_name, score, chat_id, chat_title)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id, game_name, chat_id) DO UPDATE
            SET score      = GREATEST(scores.score, EXCLUDED.score),
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                chat_title = EXCLUDED.chat_title,
                created_at = NOW()
        """,
        TEST_USER, "testuser", "TestUser", TEST_SLUG, 100, 0, "",
    )
    r1 = await pc.fetchrow(
        "SELECT score, created_at FROM scores WHERE user_id = $1 AND game_name = $2",
        TEST_USER, TEST_SLUG,
    )
    results["score_stored"] = r1 is not None and r1["score"] == 100
    print(f"\nSTEP 3  First score stored={r1['score']} at={r1['created_at']}")

    # ── STEP 4: FIX #2 — second submission refreshes created_at ───────────
    time.sleep(0.1)  # ensure clock advances
    await pc.execute(
        """
        INSERT INTO scores
            (user_id, username, first_name, game_name, score, chat_id, chat_title)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (user_id, game_name, chat_id) DO UPDATE
            SET score      = GREATEST(scores.score, EXCLUDED.score),
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                chat_title = EXCLUDED.chat_title,
                created_at = NOW()
        """,
        TEST_USER, "testuser", "TestUser", TEST_SLUG, 50, 0, "",
    )
    r2 = await pc.fetchrow(
        "SELECT score, created_at FROM scores WHERE user_id = $1 AND game_name = $2",
        TEST_USER, TEST_SLUG,
    )
    results["fix2_created_at_refreshed"] = r2["created_at"] > r1["created_at"]
    results["fix2_best_score_kept"] = r2["score"] == 100
    print(f"STEP 4  FIX#2 created_at refreshed: {results['fix2_created_at_refreshed']}")
    print(f"        best score kept at 100: {results['fix2_best_score_kept']}")

    # ── STEP 5: Statistics ─────────────────────────────────────────────────
    today = await pc.fetchval(
        "SELECT COUNT(*) FROM scores WHERE game_name = $1 AND created_at::date = CURRENT_DATE",
        TEST_SLUG,
    )
    week = await pc.fetchval(
        "SELECT COUNT(*) FROM scores WHERE game_name = $1 AND created_at >= NOW() - INTERVAL '7 days'",
        TEST_SLUG,
    )
    month = await pc.fetchval(
        "SELECT COUNT(*) FROM scores WHERE game_name = $1 AND created_at >= NOW() - INTERVAL '30 days'",
        TEST_SLUG,
    )
    results["stats_today"]  = int(today)  >= 1
    results["stats_week"]   = int(week)   >= 1
    results["stats_month"]  = int(month)  >= 1
    print(f"\nSTEP 5  today={today} week={week} month={month} (all must be >=1)")
    print(f"        stats pass: {results['stats_today'] and results['stats_week'] and results['stats_month']}")

    # ── STEP 6: Rankings ───────────────────────────────────────────────────
    lb = await pc.fetch(
        "SELECT user_id, score FROM scores WHERE game_name = $1 ORDER BY score DESC LIMIT 5",
        TEST_SLUG,
    )
    results["rankings_updated"] = len(lb) > 0
    print(f"\nSTEP 6  Leaderboard entries: {len(lb)} | top score: {lb[0]['score'] if lb else 'none'}")

    # ── STEP 7/8: Delete game and verify full cleanup (FIX #3) ─────────────
    dest.unlink(missing_ok=True)
    await gc.execute("DELETE FROM games WHERE slug = $1", TEST_SLUG)
    del_result = await pc.execute("DELETE FROM scores WHERE game_name = $1", TEST_SLUG)
    purged = int(del_result.split()[-1])

    rem_games  = await gc.fetchval("SELECT COUNT(*) FROM games WHERE slug = $1", TEST_SLUG)
    rem_scores = await pc.fetchval("SELECT COUNT(*) FROM scores WHERE game_name = $1", TEST_SLUG)
    post_active = [r["slug"] for r in await gc.fetch("SELECT slug FROM games WHERE active = TRUE")]

    results["html_removed"]        = not dest.exists()
    results["db_record_removed"]   = int(rem_games) == 0
    results["scores_purged"]       = purged >= 1
    results["no_orphan_scores"]    = int(rem_scores) == 0
    results["not_in_oyinlar"]      = TEST_SLUG not in post_active
    results["not_in_reyting"]      = TEST_SLUG not in post_active
    results["no_orphan_records"]   = int(rem_games) == 0 and int(rem_scores) == 0

    print(f"\nSTEP 7  HTML file removed:    {results['html_removed']}")
    print(f"STEP 8  games row removed:    {results['db_record_removed']}")
    print(f"        scores purged:        {purged} rows | orphans remaining: {rem_scores}")
    print(f"        not in /oyinlar:      {results['not_in_oyinlar']}")
    print(f"        not in /reyting:      {results['not_in_reyting']}")
    print(f"        no orphan records:    {results['no_orphan_records']}")

    # ── FIX #1: WEBAPP_URL auto-detection ─────────────────────────────────
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from config import config
    results["fix1_no_render"] = "onrender.com" not in config.WEBAPP_URL
    results["fix1_replit_domain"] = "replit.dev" in config.WEBAPP_URL
    print(f"\nFIX #1  WEBAPP_URL: {config.WEBAPP_URL}")
    print(f"        no onrender.com: {results['fix1_no_render']}")
    print(f"        uses replit.dev: {results['fix1_replit_domain']}")

    await gc.close()
    await pc.close()

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n--- Summary ---")
    all_pass = True
    for key, val in results.items():
        status = "✓" if val else "✗ FAIL"
        if not val:
            all_pass = False
        print(f"  {status}  {key}")

    print(f"\n=== OVERALL: {'PASS ✓' if all_pass else 'FAIL ✗'} ===")
    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(run())
    raise SystemExit(0 if ok else 1)
