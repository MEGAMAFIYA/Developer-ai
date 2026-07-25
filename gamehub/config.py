import os
from dotenv import load_dotenv

load_dotenv()

# Replit provides a single DATABASE_URL; use it for both pools unless
# the user has explicitly set separate URLs.
_default_db_url: str = os.getenv("DATABASE_URL", "")


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")

    # Accept individual overrides; fall back to the shared Replit DB.
    GLOBAL_DATABASE_URL: str = os.getenv("GLOBAL_DATABASE_URL", "") or _default_db_url
    GAME_DATABASE_URL: str   = os.getenv("GAME_DATABASE_URL",   "") or _default_db_url

    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_OWNER: str = os.getenv("GITHUB_OWNER", "")
    GITHUB_REPO: str = os.getenv("GITHUB_REPO", "")
    GITHUB_BRANCH: str = os.getenv("GITHUB_BRANCH", "main")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # AI Developer — provider, model and key (all optional; empty = disabled)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "")   # openai | openrouter | gemini | claude | deepseek
    AI_MODEL: str    = os.getenv("AI_MODEL", "")       # e.g. gpt-4o, gemini-1.5-pro, claude-3-5-sonnet
    AI_API_KEY: str  = os.getenv("AI_API_KEY", "")     # provider API key

    # Public URL for WebApp.
    # When running on Replit, REPLIT_DEV_DOMAIN is always the live domain for
    # the current deployment — it is always preferred over any statically-
    # configured WEBAPP_URL so that Play buttons and score submissions never
    # route to a stale deployment (e.g. a previous Render host).
    # On non-Replit environments (local dev, CI) we fall back to WEBAPP_URL,
    # then to localhost.
    _replit_domain: str = os.getenv("REPLIT_DEV_DOMAIN", "").strip()
    WEBAPP_URL: str = (
        f"https://{_replit_domain}"
        if _replit_domain
        else (os.getenv("WEBAPP_URL", "").strip() or "http://localhost:8000")
    )

    DEVELOPER_MODE: bool = os.getenv("DEVELOPER_MODE", "False").lower() == "true"

    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", "8000"))


config = Config()
