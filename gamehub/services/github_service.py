"""GitHub auto-push service for /yangi game uploads.

Called by handlers/admin.py after a new game is saved to disk and DB.
Uses the same asyncio subprocess pattern as
handlers/developer/modules/ai/github_tools.py — no new dependencies.

Public API
──────────
    push_game_files(slug, html_path, image_path) -> (ok: bool, message: str)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Git operations run from the workspace root (one level above gamehub/).
# gamehub/services/github_service.py
#   → .parents[0] = gamehub/services/
#   → .parents[1] = gamehub/
#   → .parents[2] = workspace/   ← git root
_GIT_ROOT = Path(__file__).resolve().parents[2]


async def _git(*args: str) -> tuple[int, str, str]:
    """Run a git subcommand from the workspace root.

    Returns (returncode, stdout, stderr).
    Mirrors the helper in handlers/developer/modules/ai/github_tools.py.
    """
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(_GIT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def _current_branch() -> str:
    rc, out, _ = await _git("branch", "--show-current")
    return out.strip() if rc == 0 else "main"


async def push_game_files(
    slug: str,
    html_path: Path,
    image_path: Path,
) -> tuple[bool, str]:
    """Commit and push new game files to the remote GitHub repository.

    Stages ONLY the two provided files (HTML + image/GIF/PNG/WEBP) so that
    unrelated working-tree changes are not accidentally committed.

    Rules
    ─────
    • git identity is set to "GameHub Bot" before every run (idempotent).
    • If git reports "nothing to commit" the function returns success=True —
      the files are already in sync with the remote.
    • Any git error returns success=False with a descriptive message; the
      caller (cb_save in admin.py) treats this as a non-fatal warning.

    Returns
    ───────
    (True,  success_message)  on success or already-synced
    (False, error_message)    on any git failure
    """
    try:
        # ── 0. Git identity (required for commits) ────────────────────────
        await _git("config", "user.email", "bot@gamehub.local")
        await _git("config", "user.name",  "GameHub Bot")

        # ── 1. Stage only the new game files ─────────────────────────────
        files_to_add: list[str] = []
        for p in (html_path, image_path):
            if p.exists():
                try:
                    files_to_add.append(str(p.relative_to(_GIT_ROOT)))
                except ValueError:
                    # path is outside the git root — skip
                    logger.warning("github_service: %s is outside git root, skipping", p)

        if not files_to_add:
            return False, "Sahna qo'shish uchun fayl topilmadi (disk da mavjud emas)"

        rc_add, _, err_add = await _git("add", *files_to_add)
        if rc_add != 0:
            return False, f"git add xatosi: {err_add.strip()}"

        # ── 2. Commit ─────────────────────────────────────────────────────
        commit_msg = f"Add game: {slug}"
        rc_commit, out_commit, err_commit = await _git("commit", "-m", commit_msg)
        if rc_commit != 0:
            combined = (out_commit + err_commit).lower()
            if "nothing to commit" in combined or "nothing added" in combined:
                # Files already committed — treat as success
                logger.info("github_service: slug=%s already committed, skipping push", slug)
                return True, "Allaqachon committed (push o'tkazib yuborildi)"
            return False, f"git commit xatosi: {(err_commit or out_commit).strip()}"

        # ── 3. Push ───────────────────────────────────────────────────────
        branch = await _current_branch()
        rc_push, out_push, err_push = await _git("push", "origin", branch)
        if rc_push != 0:
            detail = (err_push or out_push).strip()
            return False, f"git push xatosi (branch={branch}): {detail}"

        pushed = ", ".join(files_to_add)
        logger.info("github_service: pushed slug=%s branch=%s files=[%s]", slug, branch, pushed)
        return True, f"branch={branch} | {pushed}"

    except Exception as exc:
        logger.exception("github_service: unexpected error for slug=%s", slug)
        return False, f"Kutilmagan xato: {exc}"
