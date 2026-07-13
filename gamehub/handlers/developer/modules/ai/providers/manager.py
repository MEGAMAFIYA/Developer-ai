"""AI Developer — provider manager.

Single entry point for all AI operations.  Instantiate once at startup
(or lazily on first use) and call its methods identically regardless of
which backend is configured.

Usage
─────
    from handlers.developer.modules.ai.providers import AIProviderManager
    import config as cfg

    manager = AIProviderManager(
        provider_name = cfg.config.AI_PROVIDER,
        api_key       = cfg.config.AI_API_KEY,
        model         = cfg.config.AI_MODEL,
    )
    result = await manager.generate_code("make the snake faster", language="javascript")
    if result.ok:
        print(result.content)
    else:
        print(result.error)   # "API key o'rnatilmagan" etc.

Extending
─────────
Register a new provider class in _REGISTRY — everything else is automatic.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class AIProviderManager:
    """Unified facade over all AI provider implementations."""

    # ── Provider registry — add new providers here ────────────────────────────
    # Import is deferred to avoid circular imports at module load time.
    @staticmethod
    def _build_registry() -> Dict[str, Type[BaseAIProvider]]:
        from handlers.developer.modules.ai.providers.openai     import OpenAIProvider
        from handlers.developer.modules.ai.providers.openrouter import OpenRouterProvider
        from handlers.developer.modules.ai.providers.gemini     import GeminiProvider
        from handlers.developer.modules.ai.providers.claude     import ClaudeProvider
        from handlers.developer.modules.ai.providers.deepseek   import DeepSeekProvider

        return {
            "openai":      OpenAIProvider,
            "openrouter":  OpenRouterProvider,
            "gemini":      GeminiProvider,
            "claude":      ClaudeProvider,
            "deepseek":    DeepSeekProvider,
        }

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(self, provider_name: str, api_key: str, model: str) -> None:
        self._name: str = provider_name.strip().lower()
        self._provider: Optional[BaseAIProvider] = None

        if self._name:
            registry = self._build_registry()
            cls = registry.get(self._name)
            if cls:
                self._provider = cls(api_key=api_key, model=model)
                logger.info("AI provider loaded: %s (model=%s)", self._name, model or "default")
            else:
                logger.warning(
                    "Unknown AI_PROVIDER '%s'. Valid values: %s",
                    self._name,
                    ", ".join(registry),
                )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """True if a known provider is instantiated (key may still be empty)."""
        return self._provider is not None

    @property
    def active_provider(self) -> str:
        """Name of the active provider, or 'none'."""
        return self._name or "none"

    def _not_configured(self) -> AIResponse:
        return AIResponse.failure(
            error=(
                "AI provider o'rnatilmagan.\n"
                ".env da AI_PROVIDER va AI_API_KEY ni sozlang.\n"
                f"Mavjud providerlar: openai, openrouter, gemini, claude, deepseek"
            ),
            provider=self._name or "none",
            model="",
        )

    # ── Public interface (mirrors BaseAIProvider) ─────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        """Generate free-form text via the configured provider."""
        if not self._provider:
            return self._not_configured()
        return await self._provider.generate_text(prompt, **kwargs)

    async def generate_code(
        self,
        prompt: str,
        language: str = "javascript",
        **kwargs,
    ) -> AIResponse:
        """Generate source code via the configured provider."""
        if not self._provider:
            return self._not_configured()
        return await self._provider.generate_code(prompt, language=language, **kwargs)

    async def edit_code(
        self,
        original_code: str,
        instruction: str,
        **kwargs,
    ) -> AIResponse:
        """Apply an edit instruction to source code via the configured provider."""
        if not self._provider:
            return self._not_configured()
        return await self._provider.edit_code(original_code, instruction, **kwargs)

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        """Analyze source code via the configured provider."""
        if not self._provider:
            return self._not_configured()
        return await self._provider.analyze_code(code, **kwargs)

    # ── Utility ───────────────────────────────────────────────────────────────

    def status(self) -> str:
        """Human-readable status string (for /developer diagnostics)."""
        if not self._provider:
            return "❌ AI provider o'rnatilmagan"
        has_key = bool(self._provider.api_key)
        key_status = "🔑 key mavjud" if has_key else "⚠️ API key yo'q"
        return (
            f"✅ Provider: <b>{self._name}</b>\n"
            f"   Model: <code>{self._provider.model or 'default'}</code>\n"
            f"   {key_status}"
        )
