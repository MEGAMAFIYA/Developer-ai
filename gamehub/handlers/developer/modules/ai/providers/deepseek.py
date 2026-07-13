"""AI Developer — DeepSeek provider (fully implemented).

DeepSeek specialises in code generation and is very cost-effective.
Its API is OpenAI-compatible (same endpoint shape, different base URL).

Supported models (set AI_MODEL in .env or via Telegram key manager):
  deepseek-chat          — general chat, good for text + code
  deepseek-coder         — optimised for code generation (default)
  deepseek-reasoner      — chain-of-thought reasoning model (R1)

API reference: https://platform.deepseek.com/api-docs
Base URL: https://api.deepseek.com/v1/chat/completions
Auth: Authorization: Bearer {api_key}  (OpenAI-compatible)
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(BaseAIProvider):
    NAME = "deepseek"

    _DEFAULT_MODEL  = "deepseek-coder"
    _BASE_URL       = "https://api.deepseek.com/v1/chat/completions"

    _TIMEOUT_TEXT   = 60
    _TIMEOUT_CODE   = 120

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── Internal HTTP helper ───────────────────────────────────────────────────

    async def _chat(
        self,
        messages: list[dict],
        timeout: int = 60,
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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
                        return self._err("DeepSeek bo'sh javob qaytardi.")

                    if resp.status == 401:
                        return self._err(
                            "❌ Noto'g'ri API kalit (401).\n"
                            "Iltimos, DeepSeek kalitini tekshiring va qayta kiriting."
                        )
                    if resp.status == 429:
                        return self._err(
                            "⏳ So'rovlar limiti oshib ketdi (429).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )
                    if resp.status == 402:
                        return self._err(
                            "💳 DeepSeek hisobida mablag' yetarli emas (402).\n"
                            "https://platform.deepseek.com saytida to'ldiring."
                        )
                    if resp.status == 503:
                        return self._err(
                            "🔧 DeepSeek vaqtinchalik ishlamayapti (503).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )

                    body = await resp.text()
                    return self._err(
                        f"DeepSeek xatosi: HTTP {resp.status}\n"
                        f"<code>{body[:400]}</code>"
                    )

        except TimeoutError:
            return self._err(
                f"⏱ Vaqt tugadi: DeepSeek {timeout}s ichida javob bermadi."
            )
        except aiohttp.ClientConnectorError:
            return self._err(
                "🌐 Tarmoq xatosi: api.deepseek.com ga ulanib bo'lmadi."
            )
        except Exception as exc:
            logger.exception("DeepSeek unexpected error: %s", exc)
            return self._err(f"Kutilmagan xato: {exc}")

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
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
            {"role": "user", "content": instruction},
        ]
        return await self._chat(messages, timeout=self._TIMEOUT_CODE)

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
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
