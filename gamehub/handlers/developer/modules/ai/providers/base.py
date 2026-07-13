"""AI Developer — abstract base class for all AI providers.

Every provider MUST subclass BaseAIProvider and implement all four methods.
No actual network I/O happens here or in any provider stub.

Response contract
─────────────────
All methods return an AIResponse dataclass:
  ok       – True on success, False on any error
  content  – generated text / code (empty string on error)
  provider – provider NAME constant (e.g. "openai")
  model    – model identifier used for this call
  error    – human-readable Uzbek error message, or None on success

Key-check pattern (use in every method before doing anything else):
    err = self._check_key()
    if err:
        return err
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class AIResponse:
    """Unified response returned by every provider method."""
    ok: bool
    content: str
    provider: str
    model: str
    error: Optional[str] = field(default=None)

    # ── Convenience constructors ──────────────────────────────────────────────

    @classmethod
    def success(cls, content: str, provider: str, model: str) -> "AIResponse":
        return cls(ok=True, content=content, provider=provider, model=model)

    @classmethod
    def failure(cls, error: str, provider: str, model: str) -> "AIResponse":
        return cls(ok=False, content="", provider=provider, model=model, error=error)


# ── Abstract base provider ────────────────────────────────────────────────────

class BaseAIProvider(ABC):
    """Abstract base class all AI providers must inherit from.

    Constructor args
    ────────────────
    api_key : str  — provider API key (may be empty; checked per-call)
    model   : str  — model identifier (e.g. "gpt-4o", "gemini-1.5-pro")
    """

    # Subclasses MUST set this to their registry key (e.g. "openai")
    NAME: str = ""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key: str = api_key.strip()
        self.model: str   = model.strip()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _check_key(self) -> Optional[AIResponse]:
        """Return a failure response if API key is missing, else None."""
        if not self.api_key:
            return AIResponse.failure(
                error="API key o'rnatilmagan. .env da AI_API_KEY ni sozlang.",
                provider=self.NAME,
                model=self.model,
            )
        return None

    def _ok(self, content: str) -> AIResponse:
        return AIResponse.success(content, provider=self.NAME, model=self.model)

    def _err(self, message: str) -> AIResponse:
        return AIResponse.failure(message, provider=self.NAME, model=self.model)

    # ── Abstract interface — implement all four in every provider ─────────────

    @abstractmethod
    async def generate_text(self, prompt: str, **kwargs) -> AIResponse:
        """Generate free-form text from a natural-language prompt."""
        ...

    @abstractmethod
    async def generate_code(
        self,
        prompt: str,
        language: str = "javascript",
        **kwargs,
    ) -> AIResponse:
        """Generate source code from a natural-language description.

        Args:
            prompt   : what the code should do
            language : target language hint (javascript | css | html | python …)
        """
        ...

    @abstractmethod
    async def edit_code(
        self,
        original_code: str,
        instruction: str,
        **kwargs,
    ) -> AIResponse:
        """Apply an edit instruction to existing source code.

        Args:
            original_code : the full source to be modified
            instruction   : natural-language description of the change
        """
        ...

    @abstractmethod
    async def analyze_code(self, code: str, **kwargs) -> AIResponse:
        """Analyze source code and return a structured report.

        Report should cover: purpose, potential bugs, improvement suggestions.
        """
        ...
