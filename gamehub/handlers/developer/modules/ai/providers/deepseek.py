"""AI Developer — DeepSeek provider stub.

DeepSeek specialises in code generation and is very cost-effective.
Its API is OpenAI-compatible, so the openai SDK works out of the box.

Supported models (set AI_MODEL in .env):
  deepseek-chat          — general chat, good for text + code
  deepseek-coder         — optimised for code generation (recommended)
  deepseek-reasoner      — chain-of-thought reasoning model (R1)

API reference: https://platform.deepseek.com/api-docs
Base URL: https://api.deepseek.com/v1
Auth: OpenAI-compatible (Authorization: Bearer {api_key})

When implementing:
  - Use `openai` SDK with base_url="https://api.deepseek.com/v1"
  - No extra headers required
"""

from __future__ import annotations

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider


class DeepSeekProvider(BaseAIProvider):
    NAME = "deepseek"

    _DEFAULT_MODEL = "deepseek-coder"
    _BASE_URL      = "https://api.deepseek.com/v1"

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
        # )
        # return self._ok(response.choices[0].message.content)

        return self._err("DeepSeek generate_text hali amalga oshirilmagan.")

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("DeepSeek generate_code hali amalga oshirilmagan.")

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("DeepSeek edit_code hali amalga oshirilmagan.")

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("DeepSeek analyze_code hali amalga oshirilmagan.")
