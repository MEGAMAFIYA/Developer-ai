---
name: AI Developer Phase 4 architecture
description: How the AI API key is stored, loaded, and managed at runtime in the GameHub bot.
---

# AI Developer Phase 4 — API Key Management

## Rule
AI API credentials (provider, api_key, model) are stored in the `settings` PostgreSQL table (global DB), **not** hardcoded in `.env`. The `services.py` singleton is reloaded at runtime via `reload_manager()` whenever the admin changes keys through Telegram.

**Why:** Replit environment doesn't allow the bot process to write `.env` at runtime. The `settings` table survives restarts and lets the admin manage keys entirely from Telegram Developer Mode.

**How to apply:**
- On startup: `_load_ai_settings()` in `database/setup.py` reads from DB and calls `services.reload_manager()` if DB values exist.
- In Telegram: `key_manager.py` handles FSM key entry, writes to DB, calls `reload_manager()` immediately.
- New providers: register in `providers/manager.py` registry only — no other files need changing.
- `settings` table: `key VARCHAR PRIMARY KEY, value TEXT, updated_at TIMESTAMPTZ`.
