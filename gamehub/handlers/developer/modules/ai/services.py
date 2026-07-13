"""AI Developer — service layer (singleton manager + feature helpers).

All AI calls go through this module.  Handlers import helper functions from
here — they never import or instantiate providers directly.

Usage
─────
    from handlers.developer.modules.ai.services import ai_chat, ai_write_code

    result = await ai_chat("Salom, snake o'yinida tezlikni qanday oshiraman?")
    if result.ok:
        text = result.content
    else:
        text = result.error   # "API key o'rnatilmagan." etc.

Singleton
─────────
`get_manager()` creates the AIProviderManager once from config on first call.
Re-reading config each time would break if env vars change at runtime — the
singleton is intentional.  To hot-reload, restart the bot process.
"""

from __future__ import annotations

import logging
from typing import Optional

import config as cfg
from handlers.developer.modules.ai.providers import AIProviderManager, AIResponse
from handlers.developer.modules.ai import prompts

logger = logging.getLogger(__name__)

# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional[AIProviderManager] = None


def get_manager() -> AIProviderManager:
    """Return the global AIProviderManager, creating it on first call."""
    global _manager
    if _manager is None:
        _manager = AIProviderManager(
            provider_name=cfg.config.AI_PROVIDER,
            api_key=cfg.config.AI_API_KEY,
            model=cfg.config.AI_MODEL,
        )
        logger.info(
            "AIProviderManager initialised: provider=%s",
            cfg.config.AI_PROVIDER or "none",
        )
    return _manager


# ── Feature helpers ───────────────────────────────────────────────────────────
# Each function builds a full prompt and delegates to the manager.
# Handlers call exactly ONE of these functions per user request.


async def ai_chat(user_text: str) -> AIResponse:
    """💬 Free-form chat with the AI."""
    prompt = f"{prompts.CHAT_SYSTEM}\n\nSavol/topshiriq: {user_text}"
    return await get_manager().generate_text(prompt)


async def ai_write_code(task: str, language: str = "javascript") -> AIResponse:
    """📝 Generate code from a natural-language task description."""
    system = prompts.WRITE_CODE_SYSTEM
    body = prompts.WRITE_CODE_TEMPLATE.format(task=task, language=language)
    prompt = f"{system}\n\n{body}"
    return await get_manager().generate_code(prompt, language=language)


async def ai_edit_code(original_code: str, instruction: str) -> AIResponse:
    """✏️ Apply an edit instruction to existing source code."""
    system = prompts.EDIT_CODE_SYSTEM
    body = prompts.EDIT_CODE_TEMPLATE.format(
        code=original_code, instruction=instruction
    )
    prompt = f"{system}\n\n{body}"
    return await get_manager().edit_code(
        original_code=original_code,
        instruction=prompt,
    )


async def ai_analyze_code(code: str) -> AIResponse:
    """🔍 Analyse code for bugs, performance issues and security problems."""
    system = prompts.ANALYZE_CODE_SYSTEM
    body = prompts.ANALYZE_CODE_TEMPLATE.format(code=code)
    prompt = f"{system}\n\n{body}"
    return await get_manager().analyze_code(prompt)


async def ai_create_game(description: str) -> AIResponse:
    """🎮 Generate a full HTML5 game from a concept description."""
    system = prompts.CREATE_GAME_SYSTEM
    body = prompts.CREATE_GAME_TEMPLATE.format(description=description)
    prompt = f"{system}\n\n{body}"
    return await get_manager().generate_code(prompt, language="html")


async def ai_improve_game(code: str) -> AIResponse:
    """🛠 Improve an existing game's code quality, UX and performance."""
    system = prompts.IMPROVE_GAME_SYSTEM
    body = prompts.IMPROVE_GAME_TEMPLATE.format(code=code)
    prompt = f"{system}\n\n{body}"
    return await get_manager().edit_code(
        original_code=code,
        instruction=prompt,
    )


async def ai_find_bugs(code: str) -> AIResponse:
    """🧠 Find all bugs and issues in the given code."""
    system = prompts.FIND_BUG_SYSTEM
    body = prompts.FIND_BUG_TEMPLATE.format(code=code)
    prompt = f"{system}\n\n{body}"
    return await get_manager().analyze_code(prompt)


async def ai_fix_bug(code: str) -> AIResponse:
    """❌ Fix all bugs in the given code and return corrected version."""
    system = prompts.FIX_BUG_SYSTEM
    body = prompts.FIX_BUG_TEMPLATE.format(code=code)
    prompt = f"{system}\n\n{body}"
    return await get_manager().edit_code(
        original_code=code,
        instruction=prompt,
    )
