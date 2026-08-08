"""FastAPI application — serves WebApp static files and REST API."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.routes import scores as scores_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Mini O'yinlar", version="2.0.0", docs_url=None, redoc_url=None)


@app.exception_handler(RequestValidationError)
async def diagnostic_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = await request.body()
    body_text = body.decode("utf-8", errors="replace")
    logger.error(
        "422 VALIDATION ERROR\nerrors = %s\nbody = %s",
        exc.errors(),
        body_text,
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
GAMES_DIR  = WEBAPP_DIR / "games"

# Ensure directories exist before mounting
(WEBAPP_DIR / "assets" / "games").mkdir(parents=True, exist_ok=True)
GAMES_DIR.mkdir(parents=True, exist_ok=True)

if WEBAPP_DIR.exists():
    app.mount("/webapp", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")


@app.get("/")
async def serve_landing():
    """Landing page for the BotFather-registered Mini App root URL."""
    landing_file = WEBAPP_DIR / "index.html"

    if landing_file.exists():
        return FileResponse(
            str(landing_file),
            media_type="text/html"
        )

    return HTMLResponse(
        "<h1>Mini o'yinlar</h1>",
        status_code=200
    )


# ---------------------------------------------------------------------------
# Game route  GET /games/{slug}  → serves webapp/games/{slug}.html
# ---------------------------------------------------------------------------

_NOT_FOUND_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>O'yin topilmadi</title>
  <style>
    body {{ margin: 0; display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 100vh;
            background: #1a1a2e; color: #eee; font-family: sans-serif; text-align: center; }}
    h1 {{ font-size: 3rem; margin-bottom: .5rem; }}
    p  {{ font-size: 1.1rem; color: #aaa; }}
    a  {{ margin-top: 1.5rem; display: inline-block; padding: .6rem 1.4rem;
           background: #e94560; color: #fff; border-radius: 8px;
           text-decoration: none; font-weight: bold; }}
  </style>
</head>
<body>
  <h1>🎮 404</h1>
  <p>Kechirasiz, <strong>{slug}</strong> o'yini topilmadi.</p>
  <a href="javascript:window.history.back()">← Orqaga</a>
</body>
</html>"""


@app.get("/games/{slug}")
async def serve_game(slug: str):
    """Return the HTML game file for the given slug, or a friendly 404 page."""
    # Basic slug safety: only allow alphanumeric, dash, underscore
    safe = all(c.isalnum() or c in "-_" for c in slug)
    if not safe:
        return HTMLResponse(_NOT_FOUND_HTML.format(slug=slug), status_code=404)

    game_file = GAMES_DIR / f"{slug}.html"
    if game_file.exists():
        return FileResponse(str(game_file), media_type="text/html")

    return HTMLResponse(_NOT_FOUND_HTML.format(slug=slug), status_code=404)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

app.include_router(scores_router.router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check  GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    """Production health check.

    Probes both asyncpg pools with a lightweight SELECT 1 (2-second timeout).
    Returns 200 {"status":"ok"} when both pools are reachable.
    Returns 503 {"status":"degraded",...} if either pool fails — Render will
    restart the instance when this endpoint returns non-2xx.
    """
    from database.game_db   import ping as ping_game
    from database.global_db import ping as ping_global

    game_ok   = await ping_game()
    global_ok = await ping_global()

    payload = {
        "status":    "ok" if (game_ok and global_ok) else "degraded",
        "game_db":   "ok" if game_ok   else "unreachable",
        "global_db": "ok" if global_ok else "unreachable",
    }

    status_code = 200 if (game_ok and global_ok) else 503
    if status_code != 200:
        logger.warning("Health check degraded: %s", payload)

    return JSONResponse(content=payload, status_code=status_code)
