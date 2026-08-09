"""Regression tests for the Render/GitHub game persistence paths."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


GAMEHUB_DIR = Path(__file__).resolve().parents[1]
if str(GAMEHUB_DIR) not in sys.path:
    sys.path.insert(0, str(GAMEHUB_DIR))

from services import github_service
from services.project_provider import GitHubProjectProvider


CANONICAL_HTML = "gamehub/webapp/games/test-game.html"
CANONICAL_IMAGE = "gamehub/webapp/assets/games/test-game.png"
LEGACY_HTML = "webapp/games/test-game.html"
LEGACY_IMAGE = "webapp/assets/games/test-game.png"


class FakeProvider:
    def __init__(self, existing: dict[str, bytes] | None = None) -> None:
        self.files = dict(existing or {})
        self.writes: list[dict] = []

    async def get_file_bytes(
        self,
        path: str,
        *,
        preserve_repository_root: bool = False,
    ) -> tuple[bytes, str]:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path], f"sha-{path}"

    async def put_file(
        self,
        path: str,
        content: bytes,
        message: str,
        *,
        preserve_repository_root: bool = False,
    ) -> dict:
        self.writes.append(
            {
                "path": path,
                "content": content,
                "message": message,
                "preserve_repository_root": preserve_repository_root,
                "overwrite": path in self.files,
            }
        )
        self.files[path] = content
        return {"content": {"path": path}}


class GithubPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_game_writes_only_canonical_html_and_image_paths(self) -> None:
        provider = FakeProvider()
        with patch.object(github_service, "get_project_provider", return_value=provider):
            ok, _ = await github_service.push_game_files(
                "test-game",
                b"<html>new</html>",
                b"\x89PNG\r\n\x1a\nnew",
                ".png",
            )

        self.assertTrue(ok)
        self.assertEqual(
            [write["path"] for write in provider.writes],
            [CANONICAL_HTML, CANONICAL_IMAGE],
        )
        self.assertTrue(
            all(write["preserve_repository_root"] for write in provider.writes)
        )
        self.assertNotIn(LEGACY_HTML, provider.files)
        self.assertNotIn(LEGACY_IMAGE, provider.files)

    async def test_html_update_overwrites_canonical_file(self) -> None:
        provider = FakeProvider({CANONICAL_HTML: b"<html>old</html>"})
        with patch.object(github_service, "get_project_provider", return_value=provider):
            ok, _ = await github_service.push_game_html(
                "test-game",
                b"<html>updated</html>",
            )

        self.assertTrue(ok)
        self.assertEqual(provider.files[CANONICAL_HTML], b"<html>updated</html>")
        self.assertTrue(provider.writes[0]["overwrite"])
        self.assertEqual(provider.writes[0]["path"], CANONICAL_HTML)
        self.assertNotIn(LEGACY_HTML, provider.files)

    async def test_image_update_creates_or_overwrites_canonical_file(self) -> None:
        provider = FakeProvider({CANONICAL_IMAGE: b"old-image"})
        with patch.object(github_service, "get_project_provider", return_value=provider):
            ok, _ = await github_service.push_game_image(
                "test-game",
                b"new-image",
                "png",
            )

        self.assertTrue(ok)
        self.assertEqual(provider.files[CANONICAL_IMAGE], b"new-image")
        self.assertTrue(provider.writes[0]["overwrite"])
        self.assertEqual(provider.writes[0]["path"], CANONICAL_IMAGE)
        self.assertNotIn(LEGACY_IMAGE, provider.files)

    async def test_failed_github_write_is_not_reported_as_success(self) -> None:
        class FailingProvider(FakeProvider):
            async def put_file(self, *args, **kwargs):
                raise github_service.ProjectProviderError("write failed")

        provider = FailingProvider()
        with patch.object(github_service, "get_project_provider", return_value=provider):
            ok, message = await github_service.push_game_image(
                "test-game",
                b"new-image",
                ".png",
            )

        self.assertFalse(ok)
        self.assertIn("write failed", message)

    def test_repository_path_normalization_preserves_deploy_root_only_when_requested(
        self,
    ) -> None:
        self.assertEqual(
            GitHubProjectProvider.normalize_path(CANONICAL_HTML),
            "webapp/games/test-game.html",
        )
        self.assertEqual(
            GitHubProjectProvider.normalize_path(
                CANONICAL_HTML,
                preserve_repository_root=True,
            ),
            CANONICAL_HTML,
        )


if __name__ == "__main__":
    asyncio.run(unittest.main(module=None, exit=False))