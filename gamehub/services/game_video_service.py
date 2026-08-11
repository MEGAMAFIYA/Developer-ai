from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
WEBAPP_DIR = BASE_DIR / "webapp"
GAMES_DIR = WEBAPP_DIR / "games"
ASSETS_DIR = WEBAPP_DIR / "assets" / "games"

VIDEO_DIR = WEBAPP_DIR / "generated_videos"

DEFAULT_DURATION = 12


def _ensure_dirs() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


def _game_url(slug: str) -> str:
    return f"http://127.0.0.1:8000/games/{slug}"


async def create_game_mp4(
    slug: str,
    duration: int = DEFAULT_DURATION,
) -> Path:
    """
    Open the HTML game in Chromium, interact with it and record
    a short gameplay video.

    The produced MP4 is returned as a Path.
    """

    _ensure_dirs()

    if duration < 3:
        duration = 3

    if duration > 60:
        duration = 60

    raw_video = VIDEO_DIR / f"{slug}_raw.webm"
    mp4_path = ASSETS_DIR / f"{slug}.mp4"

    if raw_video.exists():
        raw_video.unlink()

    if mp4_path.exists():
        mp4_path.unlink()

    url = _game_url(slug)

    logger.info(
        "[GAME VIDEO] Starting recording: slug=%s url=%s duration=%ss",
        slug,
        url,
        duration,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium",
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 640,
                "height": 360,
            },
            device_scale_factor=1,
            record_video_dir=str(VIDEO_DIR),
            record_video_size={
                "width": 640,
                "height": 360,
            },
        )

        page = await context.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await page.wait_for_timeout(1500)

            # Try common start buttons.
            start_selectors = [
                "button:has-text('Start')",
                "button:has-text('START')",
                "button:has-text('Boshlash')",
                "button:has-text('O‘ynash')",
                "button:has-text(\"O'ynash\")",
                "#start",
                "#startButton",
                ".start-button",
                ".start-btn",
                "[data-action='start']",
            ]

            for selector in start_selectors:
                try:
                    locator = page.locator(selector).first

                    if await locator.is_visible(timeout=500):
                        await locator.click()
                        logger.info(
                            "[GAME VIDEO] Start button clicked: %s",
                            selector,
                        )
                        break

                except Exception:
                    continue

            # Basic player-like interaction.
            #
            # This is intentionally generic. More advanced game-specific
            # gameplay intelligence will be added later.
            await _simulate_player(page, duration)

            await page.wait_for_timeout(500)

        finally:
            await context.close()
            await browser.close()

    # Playwright creates a video file automatically.
    videos = sorted(
        VIDEO_DIR.glob("*.webm"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not videos:
        raise RuntimeError(
            "Chromium video recording failed: WEBM file not created."
        )

    recorded_video = videos[0]

    if recorded_video != raw_video:
        recorded_video.rename(raw_video)

    await _convert_to_mp4(
        raw_video,
        mp4_path,
    )

    try:
        raw_video.unlink()
    except OSError:
        pass

    logger.info(
        "[GAME VIDEO] MP4 created: %s",
        mp4_path,
    )

    return mp4_path


async def _simulate_player(
    page,
    duration: int,
) -> None:
    """
    Perform generic player-like actions.

    These actions do not assume a specific game.
    """

    end_time = asyncio.get_running_loop().time() + duration

    keys = [
        "ArrowRight",
        "ArrowRight",
        "Space",
        "ArrowLeft",
        "ArrowRight",
        "Space",
    ]

    index = 0

    while asyncio.get_running_loop().time() < end_time:
        key = keys[index % len(keys)]
        index += 1

        try:
            await page.keyboard.press(key)
        except Exception:
            pass

        await page.wait_for_timeout(450)

        # Try common click/tap targets.
        for selector in (
            "canvas",
            "#game",
            ".game",
            "#gameCanvas",
        ):
            try:
                target = page.locator(selector).first

                if await target.is_visible(timeout=100):
                    box = await target.bounding_box()

                    if box:
                        x = box["x"] + box["width"] * 0.5
                        y = box["y"] + box["height"] * 0.5

                        await page.mouse.click(x, y)

                        break

            except Exception:
                continue


async def _convert_to_mp4(
    source: Path,
    destination: Path,
) -> None:
    """
    Convert Playwright WEBM recording to MP4 using FFmpeg.
    """

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(destination),
    ]

    logger.info(
        "[GAME VIDEO] FFmpeg conversion started: %s",
        source,
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode(
            "utf-8",
            errors="replace",
        )

        logger.error(
            "[GAME VIDEO] FFmpeg failed: %s",
            error[-2000:],
        )

        raise RuntimeError(
            "FFmpeg MP4 conversion failed."
        )

    if not destination.exists():
        raise RuntimeError(
            "FFmpeg finished but MP4 file was not created."
        )