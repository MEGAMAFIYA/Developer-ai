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

# ── Phase 4 — File Tools (file_tools.py) ─────────────────────────────────────
AI_FILE_CREATE = "ai:file:create"   # 📂 Fayl yaratish
AI_FILE_READ   = "ai:file:read"     # 📄 Faylni o'qish
AI_FILE_EDIT   = "ai:file:edit"     # ✏️ Faylni tahrirlash
AI_FILE_DELETE = "ai:file:delete"   # 🗑 Faylni o'chirish
AI_FILE_OK     = "ai:file:ok"       # ✅ confirm write/delete
AI_FILE_PDF    = "ai:file:pdf"      # 📑 last-read faylni PDF qilib yuklash

# ── Phase 4 — GitHub Tools (github_tools.py) ──────────────────────────────────
AI_GH_CLONE  = "ai:gh:clone"        # 🌐 GitHub Clone
AI_GH_COMMIT = "ai:gh:commit"       # 📤 GitHub Commit
AI_GH_PUSH   = "ai:gh:push"         # 🚀 GitHub Push
AI_GH_PULL   = "ai:gh:pull"         # 📥 GitHub Pull
AI_GH_OK     = "ai:gh:ok"           # ✅ confirm git operation

# ── Phase 4 — Database Tools (database_tools.py) ─────────────────────────────
AI_DB_QUERY  = "ai:db:query"        # 🗄 SQL so'rov
AI_DB_STATS  = "ai:db:stats"        # 📊 Database statistikasi
AI_DB_OK     = "ai:db:ok"           # ✅ confirm DML query
AI_DB_GLOBAL = "ai:db:global"       # choose Global DB (inline button)
AI_DB_GAME   = "ai:db:game"         # choose Game DB   (inline button)

# ── Phase 4 — Project Tools (project_tools.py) ────────────────────────────────
AI_PROJ_SCAN   = "ai:proj:scan"     # 🔎 Loyihani skanerlash
AI_PROJ_MAP    = "ai:proj:map"      # 📋 Fayllar xaritasi
AI_PROJ_TEST   = "ai:proj:test"     # 🧪 To'liq test
AI_PROJ_BACKUP = "ai:proj:backup"   # 📦 Backup yaratish
AI_PROJ_OK     = "ai:proj:ok"       # ✅ confirm backup

# ── Phase 4 — Tool Manager entry points (sub-menu screens) ──────────────────
AI_FILE_MANAGER = "ai:file"          # 📂 File Manager sub-menu
AI_DB_MANAGER   = "ai:db"            # 🗄 Database Manager sub-menu
AI_GH_MANAGER   = "ai:gh"            # 🐙 GitHub Manager sub-menu
AI_PROJ_MANAGER = "ai:proj"          # 🔧 Project Manager sub-menu
AI_LOG_VIEW     = "ai:log"           # 📋 Action Log viewer

# ── Phase 4 — API Key Management (key_manager.py) ────────────────────────────
AI_KEY_SETTINGS  = "ai:key"              # 🔑 Open key management screen
AI_PROVIDER_CHANGE = "ai:key:provider"   # ✏️ Change provider (independent FSM)
AI_MODEL_CHANGE    = "ai:key:model"      # 🧠 Change model (independent FSM)
AI_KEY_CHANGE    = "ai:key:change"       # 🔑 Change API key (independent FSM)
AI_KEY_DELETE    = "ai:key:delete"       # 🗑 Prompt confirmation
AI_KEY_DELETE_OK = "ai:key:delete:ok"   # ✅ Confirm delete
AI_KEY_TEST      = "ai:key:test"         # 🔌 Test connection to provider

# ── Phase 5 — Code Assistant sub-actions ─────────────────────────────────────
AI_CODE_SAVE     = "ai:code:save"        # FSM: paste code → choose file → save
AI_CODE_SAVE_OK  = "ai:code:save:ok"     # confirm overwrite existing file

# ── Phase 5 — Game Builder ────────────────────────────────────────────────────
AI_BUILDER_SAVE    = "ai:builder:save"     # prompt for filename after generation
AI_BUILDER_DISCARD = "ai:builder:discard"  # discard generated game

# ── Phase 5 — Gameplay Designer ───────────────────────────────────────────────
AI_GAMEPLAY_LIST    = "ai:gameplay:list"    # refresh game list
AI_GAMEPLAY_SAVE_OK = "ai:gameplay:save:ok" # confirm save after AI edit
AI_GAMEPLAY_DISCARD = "ai:gameplay:discard" # discard AI result
# dynamic: "ai:gameplay:sel:<slug>" — matched via startswith in filter

# ── Phase 5 — UI Designer ────────────────────────────────────────────────────
AI_DESIGN_LIST    = "ai:design:list"
AI_DESIGN_SAVE_OK = "ai:design:save:ok"
AI_DESIGN_DISCARD = "ai:design:discard"
# dynamic: "ai:design:sel:<slug>" — matched via startswith in filter

# ── Phase 5 — Asset Generator ────────────────────────────────────────────────
AI_IMAGE_SAVE    = "ai:image:save"      # prompt for .svg filename
AI_IMAGE_DISCARD = "ai:image:discard"   # discard SVG result

# ── Phase 5 — Assets Manager ─────────────────────────────────────────────────
AI_ASSETS_LIST   = "ai:assets:list"     # refresh list
AI_ASSETS_UPLOAD = "ai:assets:upload"   # FSM: upload Document
AI_ASSETS_DEL_OK = "ai:assets:del:ok"   # confirm delete
AI_ASSETS_DEL_NO = "ai:assets:del:no"   # cancel delete
# dynamic: "ai:assets:del:<filename>" — matched via startswith

# ── Phase 5 — Preview ────────────────────────────────────────────────────────
AI_PREVIEW_LIST = "ai:preview:list"     # refresh game list

# ── Phase 5 — Test Center ────────────────────────────────────────────────────
AI_TEST_CODE = "ai:test:code"   # FSM: paste code for AI validation
AI_TEST_FILE = "ai:test:file"   # select existing game file to validate
# dynamic: "ai:test:sel:<slug>" — matched via startswith

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
    # Phase 4 — File Tools
    AI_FILE_CREATE, AI_FILE_READ, AI_FILE_EDIT, AI_FILE_DELETE, AI_FILE_OK,
    AI_FILE_PDF,
    # Phase 4 — GitHub Tools
    AI_GH_CLONE, AI_GH_COMMIT, AI_GH_PUSH, AI_GH_PULL, AI_GH_OK,
    # Phase 4 — Database Tools
    AI_DB_QUERY, AI_DB_STATS, AI_DB_OK, AI_DB_GLOBAL, AI_DB_GAME,
    # Phase 4 — Project Tools
    AI_PROJ_SCAN, AI_PROJ_MAP, AI_PROJ_TEST, AI_PROJ_BACKUP, AI_PROJ_OK,
    # Phase 4 — Tool Manager entry points
    AI_FILE_MANAGER, AI_DB_MANAGER, AI_GH_MANAGER, AI_PROJ_MANAGER, AI_LOG_VIEW,
    # Phase 4 — Key Management
    AI_KEY_SETTINGS, AI_KEY_CHANGE, AI_KEY_DELETE, AI_KEY_DELETE_OK, AI_KEY_TEST,
)
