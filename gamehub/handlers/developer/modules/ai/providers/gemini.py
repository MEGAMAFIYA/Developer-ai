"""AI Developer — Google Gemini provider (fully implemented).

Supported models (set AI_MODEL in .env or via Telegram key manager):
  gemini-1.5-pro          — best quality, large context (1M tokens)
  gemini-1.5-flash        — fast and cheap (default)
  gemini-1.5-flash-8b     — ultra-light
  gemini-2.0-flash-exp    — experimental next-gen

API reference: https://ai.google.dev/api/generate-content
Base URL: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
Auth: ?key={api_key} query parameter
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    NAME = "gemini"

    _DEFAULT_MODEL  = "gemini-1.5-flash"
    _BASE_URL       = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    _TIMEOUT_TEXT   = 60
    _TIMEOUT_CODE   = 120

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── Internal HTTP helper ───────────────────────────────────────────────────

    async def _generate(
        self,
        system_instruction: str,
        user_text: str,
        timeout: int = 60,
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        url = self._BASE_URL.format(model=self.model) + f"?key={self.api_key}"
        payload: dict = {
            "system_instruction": {
                "parts": [{"text": system_instruction}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_text}],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 8192,
            },
        }

        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = (
                                candidates[0]
                                .get("content", {})
                                .get("parts", [])
                            )
                            text: Optional[str] = parts[0].get("text") if parts else None
                            if text:
                                return self._ok(text.strip())
                        # Check for promptFeedback block
                        feedback = data.get("promptFeedback", {})
                        block_reason = feedback.get("blockReason", "")
                        if block_reason:
                            return self._err(
                                f"Gemini so'rovni blokladi: {block_reason}\n"
                                "Boshqa so'rov bilan urinib ko'ring."
                            )
                        return self._err("Gemini bo'sh javob qaytardi.")

                    if resp.status == 400:
                        body = await resp.json(content_type=None)
                        msg = body.get("error", {}).get("message", "")
                        return self._err(
                            f"❌ Noto'g'ri so'rov (400): {msg or 'unknown'}"
                        )
                    if resp.status == 401 or resp.status == 403:
                        return self._err(
                            f"❌ Noto'g'ri API kalit ({resp.status}).\n"
                            "Iltimos, Google AI Studio kalitini tekshiring."
                        )
                    if resp.status == 429:
                        return self._err(
                            "⏳ So'rovlar limiti oshib ketdi (429).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )
                    if resp.status == 503:
                        return self._err(
                            "🔧 Gemini vaqtinchalik ishlamayapti (503).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )

                    body_text = await resp.text()
                    return self._err(
                        f"Gemini xatosi: HTTP {resp.status}\n"
                        f"<code>{body_text[:400]}</code>"
                    )

        except TimeoutError:
            return self._err(
                f"⏱ Vaqt tugadi: Gemini {timeout}s ichida javob bermadi."
            )
        except aiohttp.ClientConnectorError:
            return self._err(
                "🌐 Tarmoq xatosi: generativelanguage.googleapis.com ga ulanib bo'lmadi."
            )
        except Exception as exc:
            logger.exception("Gemini unexpected error: %s", exc)
            return self._err(f"Kutilmagan xato: {exc}")

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        system = (
            "Siz GameHub Telegram o'yin platformasi uchun yordamchi AI siz. "
            "O'zbek tilida aniq, qisqa va foydali javob bering. "
            "Kerak bo'lsa ingliz tilida texnik atamalarni saqlang."
        )
        return await self._generate(system, prompt, timeout=self._TIMEOUT_TEXT)

    # ── generate_code ─────────────────────────────────────────────────────────

    async def generate_code(
        self, prompt: str, language: str = "javascript", **kwargs
    ) -> AIResponse:
        lang_upper = language.upper()
        system = (
            f"Siz tajribali {lang_upper} dasturchi siz. "
            "Faqat kod qaytaring — hech qanday izoh yoki tushuntirish yo'q, "
            "faqat markdown kod bloki ichida to'liq ishlaydigan kod. "
            "HTML5 o'yinlar uchun: bitta fayl, Telegram WebApp SDK bilan mos, "
            "Canvas API dan foydalaning, mobil qurilmalarga moslashtirilgan."
        )
        return await self._generate(system, prompt, timeout=self._TIMEOUT_CODE)

    # ── edit_code ─────────────────────────────────────────────────────────────

    async def edit_code(
        self, original_code: str, instruction: str, **kwargs
    ) -> AIResponse:
        system = (
            "Siz kod muharririsiz. Foydalanuvchi sizga mavjud kod va "
            "o'zgartirish ko'rsatmasini beradi. "
            "Faqat o'zgartirilgan to'liq kodni qaytaring — "
            "hech qanday tushuntirish yo'q, faqat kod. "
            "O'zgartirilgan joylarni `// EDIT:` izohi bilan belgilang."
        )
        return await self._generate(system, instruction, timeout=self._TIMEOUT_CODE)

    # ── analyze_code ──────────────────────────────────────────────────────────

    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        system = (
            "Siz kod auditori siz. Berilgan kodni quyidagi yo'nalishlarda tahlil qiling:\n"
            "1. 🐛 Xatolar va potensial muammolar\n"
            "2. ⚡ Samaradorlik muammolari\n"
            "3. 🔒 Xavfsizlik zaif joylari\n"
            "4. 💡 Yaxshilash tavsiyalari\n\n"
            "O'zbek tilida aniq, qisqa va amaliy javob bering. "
            "Har bir bo'lim sarlavhasi bilan ajratilgan bo'lsin."
        )
        return await self._generate(system, code, timeout=self._TIMEOUT_TEXT)
