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

from config import config

logger = logging.getLogger(__name__)

# Detect the git root by walking up from this file's location.
# Works correctly regardless of which directory the server is launched from.
def _find_git_root(start: Path) -> Path:
    """Walk up from *start* until a .git directory is found, then return that directory.
    Falls back to the workspace root (parents[2] of this file) if .git is not found.
    """
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    # Fallback: gamehub/services/ → gamehub/ → workspace/
    return Path(__file__).resolve().parents[2]

_GIT_ROOT = _find_git_root(Path(__file__).parent)


async def _git(*args: str) -> tuple[int, str, str]:
    """Run a git subcommand from the git root.

    Returns (returncode, stdout, stderr).
    Always has a 30-second timeout to prevent hangs on credential prompts.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(_GIT_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")
    except asyncio.TimeoutError:
        return -1, "", "Timeout: 30 soniya ichida git javob bermadi"
    except FileNotFoundError:
        return -1, "", "git topilmadi (PATH da yo'q)"
    except Exception as exc:
        return -1, "", str(exc)


async def _current_branch() -> str:
    """Return the current branch name.

    Falls back to config.GITHUB_BRANCH (then 'main') on detached HEAD or error.
    """
    rc, out, _ = await _git("rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return config.GITHUB_BRANCH or "main"
    branch = out.strip()
    if not branch or branch == "HEAD":
        # Detached HEAD — use configured branch
        logger.warning("[GITHUB] Detached HEAD aniqlandi — config.GITHUB_BRANCH ishlatiladi")
        return config.GITHUB_BRANCH or "main"
    return branch


def _authenticated_push_url() -> str | None:
    """Return an HTTPS URL with the token embedded for a credential-free push.

    Returns None if GITHUB_TOKEN, GITHUB_OWNER, or GITHUB_REPO are not configured.
    Never logs the token itself.
    """
    token = config.GITHUB_TOKEN
    owner = config.GITHUB_OWNER
    repo  = config.GITHUB_REPO
    if not (token and owner and repo):
        return None
    repo_name = repo.rstrip(".git")
    return f"https://{token}@github.com/{owner}/{repo_name}.git"


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
        logger.info("[GITHUB] push_game_files START: slug=%s git_root=%s", slug, _GIT_ROOT)

        # ── -1. Verify this is a git repository ───────────────────────────
        rc_check, _, err_check = await _git("rev-parse", "--is-inside-work-tree")
        if rc_check != 0:
            msg = (
                f"[GITHUB] git repozitoriyasi topilmadi "
                f"(cwd={_GIT_ROOT}): {err_check.strip()}"
            )
            logger.error(msg)
            return False, msg

        # ── -0.5. Detect detached HEAD ────────────────────────────────────
        rc_hd, hd_out, _ = await _git("rev-parse", "--abbrev-ref", "HEAD")
        if rc_hd == 0 and hd_out.strip() == "HEAD":
            logger.warning(
                "[GITHUB] Detached HEAD holati aniqlandi — "
                "config.GITHUB_BRANCH=%s ishlatiladi", config.GITHUB_BRANCH
            )

        # ── 0. Git identity (required for commits) ────────────────────────
        await _git("config", "user.email", "bot@gamehub.local")
        await _git("config", "user.name",  "GameHub Bot")

        # ── 0.5. Verify files exist on disk before staging ────────────────
        logger.info(
            "[GITHUB] HTML  path: %s | exists=%s", html_path,  html_path.exists()
        )
        logger.info(
            "[GITHUB] Image path: %s | exists=%s", image_path, image_path.exists()
        )

        if html_path.exists():
            logger.info("[GITHUB] HTML found")
        else:
            logger.warning("[GITHUB] HTML NOT FOUND: %s", html_path)

        if image_path.exists():
            logger.info("[GITHUB] Image found")
        else:
            logger.warning("[GITHUB] Image NOT FOUND: %s", image_path)

        # ── 1. Stage only the new game files ─────────────────────────────
        files_to_add: list[str] = []
        for p in (html_path, image_path):
            if p.exists():
                try:
                    files_to_add.append(str(p.relative_to(_GIT_ROOT)))
                except ValueError:
                    logger.warning(
                        "[GITHUB] %s git root tashqarisida, o'tkazib yuborildi", p
                    )

        if not files_to_add:
            msg = "[GITHUB] Sahna qo'shish uchun fayl topilmadi (disk da mavjud emas)"
            logger.error(msg)
            return False, msg

        # git status BEFORE add
        _, status_before, _ = await _git("status", "--short")
        logger.info(
            "[GITHUB] git status (before add):\n%s",
            status_before.strip() or "(clean)"
        )

        rc_add, _, err_add = await _git("add", *files_to_add)
        if rc_add != 0:
            logger.error("[GITHUB] git add FAILED: %s", err_add.strip())
            return False, f"git add xatosi: {err_add.strip()}"
        logger.info("[GITHUB] git add OK: %s", files_to_add)

        # git status AFTER add / BEFORE commit
        _, status_after_add, _ = await _git("status", "--short")
        logger.info(
            "[GITHUB] git status (after add / before commit):\n%s",
            status_after_add.strip() or "(clean)"
        )

        # ── 2. Commit ─────────────────────────────────────────────────────
        commit_msg = f"Add game: {slug}"
        rc_commit, out_commit, err_commit = await _git("commit", "-m", commit_msg)

        # git status AFTER commit
        _, status_after_commit, _ = await _git("status", "--short")
        logger.info(
            "[GITHUB] git status (after commit):\n%s",
            status_after_commit.strip() or "(clean)"
        )

        if rc_commit != 0:
            combined = (out_commit + err_commit).lower()
            if "nothing to commit" in combined or "nothing added" in combined:
                logger.info(
                    "[GITHUB] slug=%s allaqachon committed — push o'tkazib yuborildi",
                    slug,
                )
                return True, "Allaqachon committed (push o'tkazib yuborildi)"
            logger.error(
                "[GITHUB] git commit FAILED: %s",
                (err_commit or out_commit).strip()
            )
            return False, f"git commit xatosi: {(err_commit or out_commit).strip()}"
        logger.info("[GITHUB] git commit OK")

        # git log to confirm newest commit
        _, log_out, _ = await _git("log", "--oneline", "-1")
        logger.info("[GITHUB] git log --oneline -1: %s", log_out.strip())

        # ── 3. Push with authentication ───────────────────────────────────
        branch   = await _current_branch()
        auth_url = _authenticated_push_url()

        logger.info("[GITHUB] push branch: %s", branch)

        if auth_url:
            # Push to the authenticated URL without modifying the stored remote.
            # Use HEAD:{branch} so the local HEAD always maps to the correct remote branch.
            logger.info(
                "[GITHUB] push remote: https://***@github.com/%s/%s.git",
                config.GITHUB_OWNER, config.GITHUB_REPO,
            )
            rc_push, out_push, err_push = await _git(
                "push", auth_url, f"HEAD:{branch}"
            )
        else:
            # Token not configured — attempt push with stored origin (will likely fail on HTTPS)
            logger.warning(
                "[GITHUB] GITHUB_TOKEN/GITHUB_OWNER/GITHUB_REPO sozlanmagan — "
                "autentifikatsiyasiz push urinilmoqda (origin)"
            )
            rc_push, out_push, err_push = await _git("push", "origin", branch)

        logger.info("[GITHUB] push exit code: %d", rc_push)

        if rc_push != 0:
            detail = (err_push or out_push).strip()
            logger.error("[GITHUB] git push FAILED:\n%s", detail)
            return False, f"git push xatosi (branch={branch}): {detail}"

        logger.info("[GITHUB] git push OK")
        pushed = ", ".join(files_to_add)
        logger.info(
            "[GITHUB] slug=%s muvaffaqiyatli push qilindi | branch=%s | files=[%s]",
            slug, branch, pushed,
        )
        return True, f"branch={branch} | {pushed}"

    except Exception as exc:
        logger.exception("[GITHUB] kutilmagan xato: slug=%s", slug)
        return False, f"Kutilmagan xato: {exc}"
