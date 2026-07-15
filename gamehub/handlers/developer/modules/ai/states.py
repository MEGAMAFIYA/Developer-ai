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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 5 — Advanced AI Features (phase5.py)
# ══════════════════════════════════════════════════════════════════════════════

class AIBuilderStates(StatesGroup):
    waiting_description = State()   # user describes the game to build
    pending_save        = State()   # generation done; waiting for save/discard
    waiting_filename    = State()   # user types filename to save as

class AIGameplayStates(StatesGroup):
    waiting_change  = State()   # game selected; user describes gameplay change
    confirm_save    = State()   # AI done; waiting for save/discard

class AIDesignStates(StatesGroup):
    waiting_change  = State()   # game selected; user describes UI change
    confirm_save    = State()   # AI done; waiting for save/discard

class AIAssetStates(StatesGroup):
    waiting_description = State()   # user describes SVG to generate
    pending_save        = State()   # SVG generated; waiting for save/discard
    waiting_filename    = State()   # user types .svg filename

class AICodeSaveStates(StatesGroup):
    waiting_code     = State()   # user pastes code to save
    waiting_filename = State()   # user types target filename

class AITestStates(StatesGroup):
    waiting_code = State()   # user pastes HTML for AI review

class AIAssetManagerFSM(StatesGroup):
    pending_delete = State()   # confirm asset file deletion
    waiting_upload = State()   # expecting Document message
