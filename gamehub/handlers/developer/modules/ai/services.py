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
`reload_manager()` replaces the singleton with new credentials — called after
the admin saves a new API key via Telegram.
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

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


def reload_manager(provider: str, api_key: str, model: str) -> AIProviderManager:
    """Replace the singleton with fresh credentials and return the new manager.

    Called after the admin saves/changes/deletes the API key via Telegram.
    """
    global _manager
    _manager = AIProviderManager(
        provider_name=provider,
        api_key=api_key,
        model=model,
    )
    logger.info("AIProviderManager reloaded: provider=%s", provider or "none")
    return _manager


# ── Status helpers ────────────────────────────────────────────────────────────

def get_ai_status() -> dict:
    """Return a dict describing the current AI configuration state.

    Keys:
        provider   str  — provider name or ''
        model      str  — model name for display (uses display_model if available)
        has_key    bool — True if api_key is non-empty
        configured bool — True if provider is known & has key
    """
    m = get_manager()
    provider = m.active_provider if m.active_provider != "none" else ""
    has_key = bool(m._provider and m._provider.api_key) if m._provider else False
    model = m._provider.display_model if m._provider else ""
    return {
        "provider":   provider,
        "model":      model,
        "has_key":    has_key,
        "configured": bool(provider) and has_key,
    }


def build_status_text() -> str:
    """Human-readable status block for the AI key management screen."""
    s = get_ai_status()
    provider = s["provider"] or "—"
    model    = s["model"] or "—"

    if not s["provider"]:
        status_line = "❌ Provider o'rnatilmagan"
    elif not s["has_key"]:
        status_line = "❌ API key kiritilmagan"
    else:
        status_line = "✅ Ulangan"

    return (
        f"🔑 <b>AI API Sozlamalari</b>\n\n"
        f"Holat: {status_line}\n"
        f"Provider: <code>{provider}</code>\n"
        f"Model: <code>{model}</code>\n\n"
        f"<i>API key xavfsiz bazada saqlanadi va faqat sizga ko'rinadi.</i>"
    )


# ── Test connection ───────────────────────────────────────────────────────────

# Provider → (url, headers_fn, payload_fn)
_TEST_CONFIGS: dict[str, dict] = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "payload": lambda model: {
            "model": model or "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        },
        "auth": "bearer",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "payload": lambda model: {
            "model": model or "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        },
        "auth": "bearer",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "payload": lambda model: {
            "model": model or "deepseek-chat",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        },
        "auth": "bearer",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "payload": lambda model: {
            "contents": [{"parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        },
        "auth": "query",
    },
    "claude": {
        "url": "https://api.anthropic.com/v1/messages",
        "payload": lambda model: {
            "model": model or "claude-3-haiku-20240307",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Hi"}],
        },
        "auth": "anthropic",
    },
}


async def test_connection() -> AIResponse:
    """Send a minimal real request to the configured provider and return status."""
    s = get_ai_status()
    provider = s["provider"]
    model    = s["model"]

    if not provider:
        return AIResponse.failure(
            "Provider o'rnatilmagan.", provider="none", model=""
        )
    m = get_manager()
    api_key = m._provider.api_key if m._provider else ""
    if not api_key:
        return AIResponse.failure(
            "API key kiritilmagan.", provider=provider, model=model
        )

    cfg_entry = _TEST_CONFIGS.get(provider)
    if not cfg_entry:
        return AIResponse.failure(
            f"Test uchun {provider} konfiguratsiyasi topilmadi.",
            provider=provider,
            model=model,
        )

    url     = cfg_entry["url"]
    payload = cfg_entry["payload"](model)
    auth    = cfg_entry["auth"]

    # ── Gemini: test via ListModels (no model name needed, validates the key) ──
    if provider == "gemini":
        list_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"?key={api_key}"
        )
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(list_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        gc_models = [
                            entry.get("name", "").removeprefix("models/")
                            for entry in data.get("models", [])
                            if "generateContent"
                            in entry.get("supportedGenerationMethods", [])
                        ]
                        # Prime the provider's model cache if not already resolved
                        p = m._provider
                        if p and not getattr(p, "_resolved_model", None) and gc_models:
                            p._resolved_model = gc_models[0]
                            p.model = gc_models[0]
                        chosen = (
                            getattr(p, "_resolved_model", None)
                            or (gc_models[0] if gc_models else "—")
                        )
                        return AIResponse.success(
                            f"Provider: <b>gemini</b>\n"
                            f"Model: <code>{chosen}</code>\n"
                            f"Mavjud modellar: {len(gc_models)}",
                            provider=provider,
                            model=chosen,
                        )
                    body = await resp.text()
                    return AIResponse.failure(
                        f"Gemini xatosi: HTTP {resp.status}\n<code>{body[:300]}</code>",
                        provider=provider,
                        model=model,
                    )
        except aiohttp.ClientConnectorError:
            return AIResponse.failure(
                "Tarmoq xatosi: Google API ga ulanib bo'lmadi.",
                provider=provider,
                model=model,
            )
        except TimeoutError:
            return AIResponse.failure(
                "Vaqt tugadi: Google API 15 soniyada javob bermadi.",
                provider=provider,
                model=model,
            )
        except Exception as exc:
            return AIResponse.failure(
                f"Kutilmagan xato: {exc}",
                provider=provider,
                model=model,
            )

    # ── All other providers: POST to their chat endpoint ─────────────────────
    if auth == "bearer":
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    elif auth == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    else:
        headers = {"Content-Type": "application/json"}

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status in (200, 201):
                    return AIResponse.success(
                        f"Provider: <b>{provider}</b>\n"
                        f"Status: {resp.status}",
                        provider=provider,
                        model=model,
                    )
                body = await resp.text()
                return AIResponse.failure(
                    f"Provider xatosi: HTTP {resp.status}\n<code>{body[:300]}</code>",
                    provider=provider,
                    model=model,
                )
    except aiohttp.ClientConnectorError:
        return AIResponse.failure(
            "Tarmoq xatosi: providerga ulanib bo'lmadi.",
            provider=provider,
            model=model,
        )
    except TimeoutError:
        return AIResponse.failure(
            "Vaqt tugadi: provider 15 soniyada javob bermadi.",
            provider=provider,
            model=model,
        )
    except Exception as exc:
        return AIResponse.failure(
            f"Kutilmagan xato: {exc}",
            provider=provider,
            model=model,
        )


# ── Feature helpers ───────────────────────────────────────────────────────────
# Each function builds a full prompt and delegates to the manager.
# Handlers call exactly ONE of these functions per user request.
# All features check configuration via the manager — if no key is set,
# manager returns a failure response automatically.


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
