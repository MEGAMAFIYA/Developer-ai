"""AI Developer — Google Gemini provider (fully implemented).

Model selection
───────────────
On the first request this provider calls the Google ModelService ListModels API
to discover which models are actually available for the configured API key.

Priority:
  1. If AI_MODEL (configured value) appears in the available list → use it.
  2. Otherwise → fall back to the first model that supports generateContent
     (sorted by preference: flash > pro > anything else).
  3. The resolved model is cached on the instance; no extra network round-trip
     is made for subsequent requests.

API reference
─────────────
ListModels:       GET  /v1beta/models?key={api_key}
generateContent:  POST /v1beta/models/{model}:generateContent?key={api_key}
Auth: ?key={api_key} query parameter (no Authorization header needed)
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider

logger = logging.getLogger(__name__)

# How long to wait for the ListModels discovery call (seconds)
_DISCOVER_TIMEOUT = 15

# Preference order used when sorting fallback candidates
_PREFER_KEYWORDS = ("flash", "pro", "ultra")


def _sort_key(model_name: str) -> tuple[int, str]:
    """Lower index = higher preference."""
    lower = model_name.lower()
    for i, kw in enumerate(_PREFER_KEYWORDS):
        if kw in lower:
            return (i, model_name)
    return (len(_PREFER_KEYWORDS), model_name)


class GeminiProvider(BaseAIProvider):
    NAME = "gemini"

    _LIST_URL  = "https://generativelanguage.googleapis.com/v1beta/models"
    _BASE_URL  = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    _TIMEOUT_TEXT  = 60
    _TIMEOUT_CODE  = 120

    def __init__(self, api_key: str, model: str) -> None:
        # Store the configured preference (may be empty string / None)
        self._configured_model: str = (model or "").strip()
        # Resolved model is populated lazily on first request
        self._resolved_model: Optional[str] = None
        # Initialise with whatever was configured (may be empty).
        # self.model is updated to the resolved value after _resolve_model() runs.
        super().__init__(api_key, self._configured_model)

    # ── Status display ─────────────────────────────────────────────────────────

    @property
    def display_model(self) -> str:
        """Return the resolved model name for UI display.

        Before the first request: shows the configured name (if any) or
        '(auto-detect)' so the admin knows Gemini will pick one automatically.
        After first request: shows the real model name that was selected.
        """
        if self._resolved_model:
            return self._resolved_model
        if self._configured_model:
            return f"{self._configured_model} (unverified)"
        return "(auto-detect)"

    # ── Model discovery ────────────────────────────────────────────────────────

    async def _resolve_model(self) -> Optional[str]:
        """Call ListModels, pick the best available model, cache and return it.

        Returns the resolved model name (short form, e.g. 'gemini-1.5-flash'),
        or None if the API call fails (caller will surface the error).
        """
        if self._resolved_model is not None:
            return self._resolved_model

        url = f"{self._LIST_URL}?key={self.api_key}"
        try:
            timeout = aiohttp.ClientTimeout(total=_DISCOVER_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(
                            "Gemini ListModels failed: HTTP %s — %s",
                            resp.status, body[:200],
                        )
                        return None

                    data = await resp.json()

        except Exception as exc:
            logger.warning("Gemini ListModels request error: %s", exc)
            return None

        # Collect models that support generateContent
        available: list[str] = []
        for entry in data.get("models", []):
            methods = entry.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            raw_name: str = entry.get("name", "")          # e.g. "models/gemini-1.5-flash"
            short = raw_name.removeprefix("models/")        # e.g. "gemini-1.5-flash"
            if short:
                available.append(short)

        if not available:
            logger.warning("Gemini ListModels: no models with generateContent found.")
            return None

        logger.debug("Gemini available models: %s", available)

        # Priority 1: use configured model if it's in the list
        if self._configured_model and self._configured_model in available:
            chosen = self._configured_model
            logger.info(
                "Gemini model resolved: %s (configured model confirmed available)",
                chosen,
            )
        else:
            # Priority 2: fall back — sort by keyword preference, pick first
            available.sort(key=_sort_key)
            chosen = available[0]
            if self._configured_model:
                logger.warning(
                    "Gemini: configured model '%s' is not available. "
                    "Falling back to '%s'. Available: %s",
                    self._configured_model, chosen, available,
                )
            else:
                logger.info(
                    "Gemini model resolved: %s (auto-selected from %d candidates)",
                    chosen, len(available),
                )

        # Update self.model so the rest of the class uses the resolved value
        self.model = chosen
        self._resolved_model = chosen
        return chosen

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

        # Resolve model (cached after first call)
        model = await self._resolve_model()
        if model is None:
            return self._err(
                "❌ Gemini modellari ro'yxatini olishda xato.\n"
                "API kalitni va internet ulanishini tekshiring."
            )

        url = self._BASE_URL.format(model=model) + f"?key={self.api_key}"
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
                        # 400 with MODEL_NOT_FOUND → invalidate cache and surface error
                        if "not found" in msg.lower() or "MODEL_NOT_FOUND" in msg:
                            logger.warning(
                                "Gemini model '%s' returned 404/400 — clearing cache.",
                                model,
                            )
                            self._resolved_model = None
                        return self._err(
                            f"❌ Noto'g'ri so'rov (400): {msg or 'unknown'}"
                        )
                    if resp.status in (401, 403):
                        return self._err(
                            f"❌ Noto'g'ri API kalit ({resp.status}).\n"
                            "Iltimos, Google AI Studio kalitini tekshiring."
                        )
                    if resp.status == 404:
                        # Model truly not found — reset cache so next call re-discovers
                        logger.warning(
                            "Gemini model '%s' not found (404) — clearing cache.", model
                        )
                        self._resolved_model = None
                        return self._err(
                            f"❌ Model topilmadi: '{model}' (404).\n"
                            "Keyingi so'rovda avtomatik yangi model tanlanadi."
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
