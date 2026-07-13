"""AI Developer module — FSM state groups.

States are defined now so the architecture is ready for OpenAI / Claude
integration.  Until the API is wired in, no handler actually enters these
states — they are imported but unused.

Usage pattern (when implementing a feature):
    from handlers.developer.modules.ai.states import AICodeStates
    from aiogram.fsm.context import FSMContext

    @router.callback_query(lambda c: c.data == AI_CODE)
    async def cb_code_start(query: CallbackQuery, state: FSMContext):
        await state.set_state(AICodeStates.waiting_for_prompt)
        await query.message.edit_text("Qaysi o'yin uchun kod yozayin?")
"""

from aiogram.fsm.state import State, StatesGroup


# ── 🎨 Dizaynni o'zgartirish ─────────────────────────────────────────────────
class AIDesignStates(StatesGroup):
    choosing_game   = State()   # select which game to redesign
    waiting_prompt  = State()   # receive natural-language design description
    confirming      = State()   # preview generated CSS/layout before apply


# ── 🖼 Rasm almashtirish ──────────────────────────────────────────────────────
class AIImageStates(StatesGroup):
    choosing_game   = State()   # select which game's image to replace
    waiting_image   = State()   # receive new image file from admin
    confirming      = State()   # confirm replacement


# ── 🎮 Gameplayni o'zgartirish ───────────────────────────────────────────────
class AIGameplayStates(StatesGroup):
    choosing_game   = State()   # select target game
    waiting_prompt  = State()   # receive gameplay change description
    waiting_confirm = State()   # confirm before patching HTML


# ── 🧠 Kod yozish ─────────────────────────────────────────────────────────────
class AICodeStates(StatesGroup):
    choosing_game   = State()   # target game slug
    choosing_lang   = State()   # language hint (JS / CSS / HTML)
    waiting_prompt  = State()   # natural-language coding task
    showing_result  = State()   # display generated code, ask to apply


# ── 🪄 AI Builder ─────────────────────────────────────────────────────────────
class AIBuilderStates(StatesGroup):
    waiting_description = State()   # full game concept description
    waiting_genre       = State()   # arcade / puzzle / shooter …
    generating          = State()   # async generation in progress
    confirming          = State()   # review before saving


# ── 📦 Asset yuklash ──────────────────────────────────────────────────────────
class AIAssetStates(StatesGroup):
    choosing_type   = State()   # image | audio | sprite
    choosing_game   = State()   # target game slug
    waiting_file    = State()   # receive file from admin
    confirming      = State()   # confirm upload path


# ── 👁 Preview ────────────────────────────────────────────────────────────────
class AIPreviewStates(StatesGroup):
    choosing_game   = State()   # which game to preview
    showing_link    = State()   # display WebApp URL


# ── 🧪 Test ───────────────────────────────────────────────────────────────────
class AITestStates(StatesGroup):
    choosing_test   = State()   # select test type
    running         = State()   # async test execution


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 — live FSM states (wired in chat.py)
# ══════════════════════════════════════════════════════════════════════════════

# ── 💬 AI Chat ────────────────────────────────────────────────────────────────
class AIChatStates(StatesGroup):
    waiting_message     = State()   # free-form text → generate_text


# ── 📝 Kod yozdirish ──────────────────────────────────────────────────────────
class AIWriteCodeStates(StatesGroup):
    waiting_prompt      = State()   # natural-language task → generate_code


# ── ✏️ Kodni tahrirlash ───────────────────────────────────────────────────────
class AIEditCodeStates(StatesGroup):
    waiting_code        = State()   # step 1: receive original code
    waiting_instruction = State()   # step 2: receive edit instruction → edit_code


# ── 🔍 Kodni tahlil qilish ────────────────────────────────────────────────────
class AIAnalyzeCodeStates(StatesGroup):
    waiting_code        = State()   # code to analyse → analyze_code


# ── 🎮 O'yin yaratish ─────────────────────────────────────────────────────────
class AICreateGameStates(StatesGroup):
    waiting_description = State()   # game concept → generate_code(html)


# ── 🛠 O'yinni yaxshilash ──────────────────────────────────────────────────────
class AIImproveGameStates(StatesGroup):
    waiting_code        = State()   # existing game code → edit_code


# ── 🧠 Bug topish ──────────────────────────────────────────────────────────────
class AIFindBugStates(StatesGroup):
    waiting_code        = State()   # code to inspect → analyze_code


# ── ❌ Xatoni tuzatish ────────────────────────────────────────────────────────
class AIFixBugStates(StatesGroup):
    waiting_code        = State()   # buggy code → edit_code (fix)
