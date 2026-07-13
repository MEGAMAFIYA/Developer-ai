"""AI Developer — Google Gemini provider stub.

Supported models (set AI_MODEL in .env):
  gemini-1.5-pro          — best quality, large context (1M tokens)
  gemini-1.5-flash        — fast and cheap
  gemini-1.5-flash-8b     — ultra-light
  gemini-2.0-flash-exp    — experimental next-gen

API reference: https://ai.google.dev/api/generate-content
SDK: pip install google-generativeai

When implementing:
  - import google.generativeai as genai
  - genai.configure(api_key=self.api_key)
  - model = genai.GenerativeModel(self.model)
  - response = await model.generate_content_async(prompt)
  - return self._ok(response.text)
"""

from __future__ import annotations

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider


class GeminiProvider(BaseAIProvider):
    NAME = "gemini"

    _DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        # TODO: implement when API is enabled
        # import google.generativeai as genai
        # genai.configure(api_key=self.api_key)
        # model = genai.GenerativeModel(self.model)
        # response = await model.generate_content_async(prompt)
        # return self._ok(response.text)

        return self._err("Gemini generate_text hali amalga oshirilmagan.")

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("Gemini generate_code hali amalga oshirilmagan.")

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("Gemini edit_code hali amalga oshirilmagan.")

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("Gemini analyze_code hali amalga oshirilmagan.")
