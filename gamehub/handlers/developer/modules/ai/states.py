"""AI Developer module — FSM state groups.

Only live states are kept here.  Each state group is wired to handlers
in chat.py (Phase 3) or key_manager.py (Phase 4).

Usage pattern:
    from handlers.developer.modules.ai.states import AIChatStates
    await state.set_state(AIChatStates.waiting_message)
"""

from aiogram.fsm.state import State, StatesGroup


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 — AI chat / code / game features (all wired in chat.py)
# ══════════════════════════════════════════════════════════════════════════════

class AIChatStates(StatesGroup):
    waiting_message     = State()   # free-form text → generate_text


class AIWriteCodeStates(StatesGroup):
    waiting_prompt      = State()   # natural-language task → generate_code


class AIEditCodeStates(StatesGroup):
    waiting_code        = State()   # step 1: receive original code
    waiting_instruction = State()   # step 2: receive edit instruction → edit_code


class AIAnalyzeCodeStates(StatesGroup):
    waiting_code        = State()   # code to analyse → analyze_code


class AICreateGameStates(StatesGroup):
    waiting_description = State()   # game concept → generate_code(html)


class AIImproveGameStates(StatesGroup):
    waiting_code        = State()   # existing game code → edit_code


class AIFindBugStates(StatesGroup):
    waiting_code        = State()   # code to inspect → analyze_code


class AIFixBugStates(StatesGroup):
    waiting_code        = State()   # buggy code → edit_code (fix)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4 — API Key Management (key_manager.py)
# ══════════════════════════════════════════════════════════════════════════════

class AIKeyStates(StatesGroup):
    waiting_key         = State()   # admin enters a new API key (+ optional provider prefix)
