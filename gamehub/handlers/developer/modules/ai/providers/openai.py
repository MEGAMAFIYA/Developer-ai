"""AI Developer — OpenAI provider stub.

Supported models (set AI_MODEL in .env):
  gpt-4o            — recommended, best quality
  gpt-4o-mini       — faster, cheaper
  gpt-4-turbo       — previous generation flagship
  gpt-3.5-turbo     — legacy, low cost

API reference: https://platform.openai.com/docs/api-reference

When implementing:
  - Use `openai` Python SDK (pip install openai)
  - Base URL: https://api.openai.com/v1
  - Auth header: Authorization: Bearer {api_key}
  - Chat completions endpoint: POST /chat/completions
"""

from __future__ import annotations

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    NAME = "openai"

    _DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        """POST /chat/completions — free-form text generation."""
        err = self._check_key()
        if err:
            return err

        # TODO: implement when API is enabled
        # from openai import AsyncOpenAI
        # client = AsyncOpenAI(api_key=self.api_key)
        # response = await client.chat.completions.create(
        #     model=self.model,
        #     messages=[{"role": "user", "content": prompt}],
        #     **kwargs,
        # )
        # return self._ok(response.choices[0].message.content)

        return self._err("OpenAI generate_text hali amalga oshirilmagan.")

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        """Generate source code with a language-aware system prompt."""
        err = self._check_key()
        if err:
            return err

        # TODO: system prompt → "You are an expert {language} developer..."
        return self._err("OpenAI generate_code hali amalga oshirilmagan.")

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        """Return only the modified source; original is sent as context."""
        err = self._check_key()
        if err:
            return err

        # TODO: two-message prompt: system + user with original + instruction
        return self._err("OpenAI edit_code hali amalga oshirilmagan.")

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        """Structured analysis: purpose, bugs, improvements."""
        err = self._check_key()
        if err:
            return err

        # TODO: structured output via response_format={"type": "json_object"}
        return self._err("OpenAI analyze_code hali amalga oshirilmagan.")
