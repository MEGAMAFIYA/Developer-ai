# Mini O'yinlar — Telegram Mini Games Bot

A Telegram mini-games bot built with **aiogram 3** (polling) and **FastAPI** (uvicorn), written in Uzbek.

## Stack

| Layer | Technology |
|-------|-----------|
| Bot framework | aiogram 3 |
| Web server | FastAPI + uvicorn |
| Databases | PostgreSQL via asyncpg (Neon) |
| Games | HTML5 Canvas / WebApp |

## Project layout

```
gamehub/
├── main.py              # Entry point — runs bot + web server concurrently
├── config.py            # Settings loaded from .env
├── requirements.txt
├── bot/
│   ├── router.py        # Combines all aiogram routers
│   └── handlers/
│       ├── start.py     # /start
│       ├── admin.py     # /yangi (admin FSM, step-by-step)
│       └── games.py     # /oyinlar [game_name]
├── db/
│   ├── global_db.py     # Global DB — game catalogue (asyncpg pool)
│   ├── game_db.py       # Game DB  — player scores (asyncpg pool)
│   └── setup.py         # Table creation + initial game seed
├── api/
│   ├── app.py           # FastAPI app, static mount, CORS
│   └── routes/
│       └── scores.py    # POST /api/scores (validates Telegram initData)
└── webapp/
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
| `ADMIN_ID` | Telegram user ID of the admin |
| `BOT_USERNAME` | Bot's @username |
| `GLOBAL_DATABASE_URL` | PostgreSQL URL for game catalogue |
| `GAME_DATABASE_URL` | PostgreSQL URL for player scores |
| `WEBAPP_URL` | Public HTTPS base URL (auto-detected from `REPLIT_DEV_DOMAIN` if blank) |
| `SECRET_KEY` | App secret key |

## Bot commands

| Command | Who | Description |
|---------|-----|-------------|
| `/start` | Anyone | Welcome message |
| `/oyinlar` | Anyone | List all available games |
| `/oyinlar <name>` | Anyone | Send a WebApp button for the game |
| `/yangi` | Admin only | Add a new game (step-by-step FSM) |
| `/bekor` | Admin (during FSM) | Cancel the add-game flow |

## Score submission

Each game calls `POST /api/scores` with `{ game, score, init_data }` at game-over.  
The server validates the Telegram WebApp `initData` via HMAC-SHA256 using the bot token,  
then saves the score to the Game PostgreSQL database.

## User preferences

- Keep existing project structure under `gamehub/`
- Use Python with aiogram 3 + FastAPI
- Use asyncpg for PostgreSQL connections (no ORM)
- Keep all text/comments in Uzbek where relevant
