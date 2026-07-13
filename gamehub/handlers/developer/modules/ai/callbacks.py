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
)
