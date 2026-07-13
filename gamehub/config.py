import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")

    GLOBAL_DATABASE_URL: str = os.getenv("GLOBAL_DATABASE_URL", "")
    GAME_DATABASE_URL: str = os.getenv("GAME_DATABASE_URL", "")

    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_OWNER: str = os.getenv("GITHUB_OWNER", "")
    GITHUB_REPO: str = os.getenv("GITHUB_REPO", "")
    GITHUB_BRANCH: str = os.getenv("GITHUB_BRANCH", "main")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # AI Developer — provider, model and key (all optional; empty = disabled)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "")   # openai | openrouter | gemini | claude | deepseek
    AI_MODEL: str    = os.getenv("AI_MODEL", "")       # e.g. gpt-4o, gemini-1.5-pro, claude-3-5-sonnet
    AI_API_KEY: str  = os.getenv("AI_API_KEY", "")     # provider API key

    # Public URL for WebApp — prefer WEBAPP_URL from .env if non-empty, else Replit domain
    WEBAPP_URL: str = os.getenv("WEBAPP_URL", "").strip() or \
        f"https://{os.getenv('REPLIT_DEV_DOMAIN', 'localhost:8000')}"

    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", "8000"))


config = Config()
