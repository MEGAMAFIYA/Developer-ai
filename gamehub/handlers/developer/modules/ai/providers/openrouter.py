"""AI Developer — OpenRouter provider (fully implemented).

OpenRouter is an API aggregator — one key gives access to 100+ models
(OpenAI, Anthropic, Google, Meta, Mistral, etc.).

Supported models examples (set AI_MODEL in .env or via Telegram key manager):
  openai/gpt-4o
  anthropic/claude-3-5-sonnet
  google/gemini-flash-1.5
  meta-llama/llama-3.1-405b-instruct
  mistralai/mixtral-8x7b-instruct
  deepseek/deepseek-coder

API reference: https://openrouter.ai/docs
Base URL: https://openrouter.ai/api/v1/chat/completions
Auth: Authorization: Bearer {api_key}
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseAIProvider):
    NAME = "openrouter"

    _DEFAULT_MODEL = "qwen/qwen3-coder:free"
    _BASE_URL       = "https://openrouter.ai/api/v1/chat/completions"
    _SITE_URL       = ""
    _SITE_NAME      = "GameHub Bot"

    # Timeouts (seconds)
    _TIMEOUT_TEXT   = 60
    _TIMEOUT_CODE   = 120   # code/game generation can be slow

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── Internal HTTP helper ───────────────────────────────────────────────────

    async def _chat(
        self,
        messages: list[dict],
        timeout: int = 60,
    ) -> AIResponse:
        """POST to OpenRouter chat completions endpoint and parse response."""
        err = self._check_key()
        if err:
            return err

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._SITE_URL,
            "X-Title": self._SITE_NAME,
        }
        payload = {
            "model": self.model,
            "messages": messages,
        }

        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(
                    self._BASE_URL,
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content: Optional[str] = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content")
                        )
                        if content:
                            return self._ok(content.strip())
                        return self._err("OpenRouter bo'sh javob qaytardi.")

                    if resp.status == 401:
                        return self._err(
                            "❌ Noto'g'ri API kalit (401).\n"
                            "Iltimos, kalitni tekshiring va qayta kiriting."
                        )
                    if resp.status == 429:
                        return self._err(
                            "⏳ So'rovlar limiti oshib ketdi (429).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )
                    if resp.status == 402:
                        return self._err(
                            "💳 OpenRouter hisobida mablag' yetarli emas (402).\n"
                            "https://openrouter.ai/credits saytida to'ldiring."
                        )

                    body = await resp.text()
                    return self._err(
                        f"OpenRouter xatosi: HTTP {resp.status}\n"
                        f"<code>{body[:400]}</code>"
                    )

        except TimeoutError:
            return self._err(
                f"⏱ Vaqt tugadi: OpenRouter {timeout}s ichida javob bermadi."
            )
        except aiohttp.ClientConnectorError:
            return self._err(
                "🌐 Tarmoq xatosi: openrouter.ai ga ulanib bo'lmadi."
            )
        except Exception as exc:
            logger.exception("OpenRouter unexpected error: %s", exc)
            return self._err(f"Kutilmagan xato: {exc}")

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        """Free-form text generation (AI Chat, analysis, etc.)."""
        messages = [
            {
                "role": "system",
                "content": (
                    "Siz GameHub Telegram o'yin platformasi uchun yordamchi AI siz. "
                    "O'zbek tilida aniq, qisqa va foydali javob bering. "
                    "Kerak bo'lsa ingliz tilida texnik atamalarni saqlang."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        return await self._chat(messages, timeout=self._TIMEOUT_TEXT)

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        """Generate source code for the given language."""
        lang_upper = language.upper()
        messages = [
            {
                "role": "system",
                "content": (
                    f"Siz tajribali {lang_upper} dasturchi siz. "
                    "Faqat kod qaytaring — hech qanday izoh yoki tushuntirish yo'q, "
                    "faqat markdown kod bloki ichida to'liq ishlaydigan kod. "
                    "HTML5 o'yinlar uchun: bitta fayl, Telegram WebApp SDK bilan mos, "
                    "Canvas API dan foydalaning, mobil qurilmalarga moslashtirilgan."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        return await self._chat(messages, timeout=self._TIMEOUT_CODE)

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        """Apply an edit instruction to existing source code."""
        messages = [
            {
                "role": "system",
                "content": (
                    "Siz kod muharririsiz. Foydalanuvchi sizga mavjud kod va "
                    "o'zgartirish ko'rsatmasini beradi. "
                    "Faqat o'zgartirilgan to'liq kodni qaytaring — "
                    "hech qanday tushuntirish yo'q, faqat kod. "
                    "O'zgartirilgan joylarni `// EDIT:` izohi bilan belgilang."
                ),
            },
            {
                "role": "user",
                "content": instruction,
            },
        ]
        return await self._chat(messages, timeout=self._TIMEOUT_CODE)

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        """Structured analysis: bugs, performance, security, improvements."""
        messages = [
            {
                "role": "system",
                "content": (
                    "Siz kod auditori siz. Berilgan kodni quyidagi yo'nalishlarda tahlil qiling:\n"
                    "1. 🐛 Xatolar va potensial muammolar\n"
                    "2. ⚡ Samaradorlik muammolari\n"
                    "3. 🔒 Xavfsizlik zaif joylari\n"
                    "4. 💡 Yaxshilash tavsiyalari\n\n"
                    "O'zbek tilida aniq, qisqa va amaliy javob bering. "
                    "Har bir bo'lim sarlavhasi bilan ajratilgan bo'lsin."
                ),
            },
            {"role": "user", "content": code},
        ]
        return await self._chat(messages, timeout=self._TIMEOUT_TEXT)
