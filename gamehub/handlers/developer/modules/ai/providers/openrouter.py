"""AI Developer — OpenRouter provider stub.

OpenRouter is an API aggregator — one key gives access to 100+ models
(OpenAI, Anthropic, Google, Meta, Mistral, etc.).

Supported models examples (set AI_MODEL in .env):
  openai/gpt-4o
  anthropic/claude-3-5-sonnet
  google/gemini-flash-1.5
  meta-llama/llama-3.1-405b-instruct
  mistralai/mixtral-8x7b-instruct
  deepseek/deepseek-coder

API reference: https://openrouter.ai/docs
Base URL: https://openrouter.ai/api/v1
Auth: same as OpenAI SDK (just change base_url)

When implementing:
  - Use `openai` SDK with base_url="https://openrouter.ai/api/v1"
  - Add headers: HTTP-Referer and X-Title for OpenRouter analytics
"""

from __future__ import annotations

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider


class OpenRouterProvider(BaseAIProvider):
    NAME = "openrouter"

    _DEFAULT_MODEL  = "openai/gpt-4o"
    _BASE_URL       = "https://openrouter.ai/api/v1"
    _SITE_URL       = ""    # set to your app URL for OpenRouter analytics
    _SITE_NAME      = "GameHub Bot"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        # TODO: implement when API is enabled
        # from openai import AsyncOpenAI
        # client = AsyncOpenAI(api_key=self.api_key, base_url=self._BASE_URL)
        # response = await client.chat.completions.create(
        #     model=self.model,
        #     messages=[{"role": "user", "content": prompt}],
        #     extra_headers={
        #         "HTTP-Referer": self._SITE_URL,
        #         "X-Title": self._SITE_NAME,
        #     },
        # )
        # return self._ok(response.choices[0].message.content)

        return self._err("OpenRouter generate_text hali amalga oshirilmagan.")

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("OpenRouter generate_code hali amalga oshirilmagan.")

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("OpenRouter edit_code hali amalga oshirilmagan.")

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("OpenRouter analyze_code hali amalga oshirilmagan.")
