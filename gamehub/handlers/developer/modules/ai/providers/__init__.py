"""AI Developer — providers sub-package.

Public surface (import from here):

    from handlers.developer.modules.ai.providers import AIProviderManager
    from handlers.developer.modules.ai.providers.base import AIResponse

Adding a new provider
─────────────────────
1. Create  providers/<name>.py  — subclass BaseAIProvider, set NAME = "<name>"
2. Register it in  providers/manager.py  → AIProviderManager._REGISTRY
3. Done — no other files need changing.
"""

from handlers.developer.modules.ai.providers.base import AIResponse, BaseAIProvider
from handlers.developer.modules.ai.providers.manager import AIProviderManager

__all__ = ["AIResponse", "BaseAIProvider", "AIProviderManager"]
