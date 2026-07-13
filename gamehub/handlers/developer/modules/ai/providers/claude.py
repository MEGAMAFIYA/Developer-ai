"""AI Developer — Anthropic Claude provider (fully implemented).

Supported models (set AI_MODEL in .env or via Telegram key manager):
  claude-3-5-sonnet-20241022   — best quality (recommended)
  claude-3-5-haiku-20241022    — fast and affordable (default)
  claude-3-opus-20240229       — most capable, slower
  claude-3-haiku-20240307      — legacy fast model

API reference: https://docs.anthropic.com/en/api
Base URL: https://api.anthropic.com/v1/messages
Auth: x-api-key header + anthropic-version header

Note: Claude uses a `system` top-level parameter (not inside messages list).
      `max_tokens` is required for every request.
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseAIProvider):
    NAME = "claude"

    _DEFAULT_MODEL      = "claude-3-5-haiku-20241022"
    _BASE_URL           = "https://api.anthropic.com/v1/messages"
    _ANTHROPIC_VERSION  = "2023-06-01"
    _MAX_TOKENS         = 8192

    _TIMEOUT_TEXT       = 60
    _TIMEOUT_CODE       = 120

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key, model or self._DEFAULT_MODEL)

    # ── Internal HTTP helper ───────────────────────────────────────────────────

    async def _chat(
        self,
        system: str,
        user_text: str,
        timeout: int = 60,
    ) -> AIResponse:
        err = self._check_key()
        if err:
            return err

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self._ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self._MAX_TOKENS,
            "system": system,
            "messages": [
                {"role": "user", "content": user_text},
            ],
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
                        content_blocks = data.get("content", [])
                        text: Optional[str] = None
                        for block in content_blocks:
                            if block.get("type") == "text":
                                text = block.get("text")
                                break
                        if text:
                            return self._ok(text.strip())
                        return self._err("Claude bo'sh javob qaytardi.")

                    if resp.status == 401:
                        return self._err(
                            "❌ Noto'g'ri API kalit (401).\n"
                            "Iltimos, Anthropic kalitini tekshiring va qayta kiriting."
                        )
                    if resp.status == 403:
                        return self._err(
                            "❌ Ruxsat yo'q (403).\n"
                            "API kalitda ushbu model uchun ruxsat mavjud emas."
                        )
                    if resp.status == 429:
                        return self._err(
                            "⏳ So'rovlar limiti oshib ketdi (429).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )
                    if resp.status == 529:
                        return self._err(
                            "🔧 Claude hozir juda band (529 — overloaded).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )
                    if resp.status == 500 or resp.status == 503:
                        return self._err(
                            f"🔧 Anthropic server xatosi ({resp.status}).\n"
                            "Bir oz kuting va qayta urinib ko'ring."
                        )

                    body = await resp.text()
                    return self._err(
                        f"Claude xatosi: HTTP {resp.status}\n"
                        f"<code>{body[:400]}</code>"
                    )

        except TimeoutError:
            return self._err(
                f"⏱ Vaqt tugadi: Claude {timeout}s ichida javob bermadi."
            )
        except aiohttp.ClientConnectorError:
            return self._err(
                "🌐 Tarmoq xatosi: api.anthropic.com ga ulanib bo'lmadi."
            )
        except Exception as exc:
            logger.exception("Claude unexpected error: %s", exc)
            return self._err(f"Kutilmagan xato: {exc}")

    # ── generate_text ─────────────────────────────────────────────────────────

    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        system = (
            "Siz GameHub Telegram o'yin platformasi uchun yordamchi AI siz. "
            "O'zbek tilida aniq, qisqa va foydali javob bering. "
            "Kerak bo'lsa ingliz tilida texnik atamalarni saqlang."
        )
        return await self._chat(system, prompt, timeout=self._TIMEOUT_TEXT)

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
        return await self._chat(system, prompt, timeout=self._TIMEOUT_CODE)

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
        return await self._chat(system, instruction, timeout=self._TIMEOUT_CODE)

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
        return await self._chat(system, code, timeout=self._TIMEOUT_TEXT)
