# Mini O'yinlar — Telegram Mini Games Bot

Telegram mini-games bot built with **aiogram 3** (polling) + **FastAPI** (uvicorn), written in Uzbek.

## Stack

| Layer | Technology |
|-------|-----------|
| Bot framework | aiogram 3 |
| Web server | FastAPI + uvicorn |
| Databases | PostgreSQL via asyncpg (Neon) |
| Games | HTML5 Canvas / Telegram WebApp |

## Project layout

```
gamehub/
├── main.py              # Entry point — runs bot + server concurrently
├── config.py            # Settings from .env (WEBAPP_URL auto-detected)
├── requirements.txt
├── bot/
│   └── router.py        # Aggregates all handlers into one aiogram router
├── database/
│   ├── global_db.py     # Global DB — game catalogue (asyncpg pool)
│   ├── game_db.py       # Game DB  — player scores (asyncpg pool)
│   └── setup.py         # Schema migration + initial seed
├── handlers/
│   ├── start.py         # /start
│   ├── admin.py         # /yangi (admin 6-step FSM)
│   └── games.py         # /oyinlar [slug]
├── services/
│   └── game_service.py  # send_game_card() — photo/text with WebApp button
├── api/
│   ├── app.py           # FastAPI app, static mount (/webapp), CORS
│   └── routes/
│       └── scores.py    # POST /api/scores (validates Telegram initData)
└── webapp/
    ├── assets/
    │   └── games/       # Admin-uploaded game images stored here
    └── games/
        ├── ilon.html    # Snake game
        └── zombi.html   # Zombie survival game
```

## How to run

```bash
cd gamehub
pip install -r requirements.txt
python main.py
```

## Environment variables (`.env`)

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token |
| `ADMIN_ID` | Admin's Telegram user ID |
| `BOT_USERNAME` | Bot's @username |
| `GLOBAL_DATABASE_URL` | PostgreSQL URL — game catalogue |
| `GAME_DATABASE_URL` | PostgreSQL URL — player scores |
| `WEBAPP_URL` | Public HTTPS base URL (auto-detected from `REPLIT_DEV_DOMAIN` if blank) |
| `SECRET_KEY` | App secret key |

## Database schema

### Global DB — `games` table
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| slug | VARCHAR(64) UNIQUE | URL-safe identifier (e.g. `snake`) |
| name | VARCHAR(128) | Display name with emoji |
| description | TEXT | Short description |
| image_url | VARCHAR(512) | `/webapp/assets/games/{slug}.jpg` or HTTP URL |
| html_file | VARCHAR(256) | Filename in `webapp/games/` (e.g. `ilon.html`) |
| category | VARCHAR(64) | Genre tag (arcade, puzzle, action…) |
| active | BOOLEAN | Whether the game appears in /oyinlar |
| created_at | TIMESTAMPTZ | Creation timestamp |

### Game DB — `scores` table
Standard per-user score records keyed by `game_name` (matches slug).

## Bot commands

| Command | Who | Description |
|---------|-----|-------------|
| `/start` | Anyone | Welcome message |
| `/oyinlar` | Anyone | Send all active games as photo cards |
| `/oyinlar <slug>` | Anyone | Send one game card |
| `/yangi` | Admin only | Add a new game (6-step FSM) |
| `/bekor` | Admin (FSM) | Cancel the add-game flow |

## Admin `/yangi` flow (6 steps)
1. **Name** — display name (e.g. `🐍 Ilon O'yini`)
2. **Slug** — unique ID (lowercase, letters/numbers/hyphens)
3. **Description** — short text shown in the card caption
4. **Category** — genre (arcade, puzzle, action, strategy, sport…)
5. **Image** — photo upload → saved to `webapp/assets/games/{slug}.jpg`
6. **HTML file** — filename in `webapp/games/` (e.g. `zombi.html`)

Game is live immediately after saving — no restart needed.

## Score submission (WebApp → API)

Each game calls `POST /api/scores` with `{ game, score, init_data }` at game-over.
Server validates the Telegram WebApp `initData` via HMAC-SHA256 (bot token), then saves.

## User preferences

- Keep existing project structure under `gamehub/`
- Python: aiogram 3 + FastAPI, asyncpg (no ORM)
- Module layout: `database/`, `handlers/`, `services/`, `bot/`, `api/`, `webapp/`
- Uzbek text in user-facing messages
