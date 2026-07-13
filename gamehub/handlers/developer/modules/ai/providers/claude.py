"""AI Developer — Anthropic Claude provider stub.

Supported models (set AI_MODEL in .env):
  claude-3-5-sonnet-20241022   — best quality (recommended)
  claude-3-5-haiku-20241022    — fast and affordable
  claude-3-opus-20240229       — most capable, slower
  claude-3-haiku-20240307      — legacy fast model

API reference: https://docs.anthropic.com/en/api
SDK: pip install anthropic

When implementing:
  - import anthropic
  - client = anthropic.AsyncAnthropic(api_key=self.api_key)
  - message = await client.messages.create(
        model=self.model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
  - return self._ok(message.content[0].text)

Note: Claude uses `messages` API (not `chat.completions`).
      System prompts go in the `system` parameter, not in messages list.
"""

from __future__ import annotations

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider


class ClaudeProvider(BaseAIProvider):
    NAME = "claude"

    _DEFAULT_MODEL  = "claude-3-5-haiku-20241022"
    _MAX_TOKENS     = 4096

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        # TODO: implement when API is enabled
        # import anthropic
        # client = anthropic.AsyncAnthropic(api_key=self.api_key)
        # message = await client.messages.create(
        #     model=self.model,
        #     max_tokens=self._MAX_TOKENS,
        #     messages=[{"role": "user", "content": prompt}],
        # )
        # return self._ok(message.content[0].text)

        return self._err("Claude generate_text hali amalga oshirilmagan.")

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        # TODO: system="You are an expert {language} developer..."
        return self._err("Claude generate_code hali amalga oshirilmagan.")

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("Claude edit_code hali amalga oshirilmagan.")

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        return self._err("Claude analyze_code hali amalga oshirilmagan.")
