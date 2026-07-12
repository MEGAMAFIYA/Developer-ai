"""FastAPI application — serves WebApp static files and REST API."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.routes import scores as scores_router

app = FastAPI(title="Mini O'yinlar", version="2.0.0", docs_url=None, redoc_url=None)

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

# Ensure assets directory exists before mounting
(WEBAPP_DIR / "assets" / "games").mkdir(parents=True, exist_ok=True)

if WEBAPP_DIR.exists():
    app.mount("/webapp", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

app.include_router(scores_router.router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
