"""AI Developer module — callback data constants.

Naming convention: ai:<action>
  ai:menu      → show AI Developer sub-menu (entry / back)
  ai:<feature> → open a specific AI feature

When a feature grows its own sub-steps, extend it here:
  e.g.  AI_CODE_PYTHON   = "ai:code:python"
        AI_CODE_JS       = "ai:code:js"
        AI_ASSETS_IMAGE  = "ai:assets:image"
        AI_ASSETS_AUDIO  = "ai:assets:audio"
        AI_ASSETS_SPRITE = "ai:assets:sprite"
"""

# ── Sub-menu navigation ───────────────────────────────────────────────────────
AI_MENU = "ai:menu"          # back-to-AI-menu button inside every sub-feature

# ── Feature entry points ──────────────────────────────────────────────────────
AI_DESIGN   = "ai:design"    # 🎨 Dizaynni o'zgartirish
AI_IMAGE    = "ai:image"     # 🖼 Rasm almashtirish
AI_GAMEPLAY = "ai:gameplay"  # 🎮 Gameplayni o'zgartirish
AI_CODE     = "ai:code"      # 🧠 Kod yozish
AI_BUILDER  = "ai:builder"   # 🪄 AI Builder
AI_ASSETS   = "ai:assets"    # 📦 Asset yuklash
AI_PREVIEW  = "ai:preview"   # 👁 Preview
AI_TEST     = "ai:test"      # 🧪 Test

# ── Phase 3 — live FSM features (chat.py) ────────────────────────────────────
AI_CANCEL       = "ai:cancel"        # ❌ Bekor qilish (clears FSM, back to menu)
AI_CHAT         = "ai:chat"          # 💬 AI Chat
AI_WRITE_CODE   = "ai:write_code"    # 📝 Kod yozdirish
AI_EDIT_CODE    = "ai:edit_code"     # ✏️ Kodni tahrirlash
AI_ANALYZE_CODE = "ai:analyze_code"  # 🔍 Kodni tahlil qilish
AI_CREATE_GAME  = "ai:create_game"   # 🎮 O'yin yaratish
AI_IMPROVE_GAME = "ai:improve_game"  # 🛠 O'yinni yaxshilash
AI_FIND_BUG     = "ai:find_bug"      # 🧠 Bug topish
AI_FIX_BUG      = "ai:fix_bug"       # ❌ Xatoni tuzatish

# ── Flat list for middleware / tests ─────────────────────────────────────────
ALL_AI_CALLBACKS = (
    AI_DESIGN,
    AI_IMAGE,
    AI_GAMEPLAY,
    AI_CODE,
    AI_BUILDER,
    AI_ASSETS,
    AI_PREVIEW,
    AI_TEST,
    # Phase 3
    AI_CANCEL,
    AI_CHAT,
    AI_WRITE_CODE,
    AI_EDIT_CODE,
    AI_ANALYZE_CODE,
    AI_CREATE_GAME,
    AI_IMPROVE_GAME,
    AI_FIND_BUG,
    AI_FIX_BUG,
)
