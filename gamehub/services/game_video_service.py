from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
VIDEO_DIR = BASE_DIR / "webapp" / "generated_videos"

DEFAULT_DURATION = 12


def _ensure_dirs() -> None:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


async def create_game_mp4(
    slug: str,
    html_bytes: bytes,
    duration: int = DEFAULT_DURATION,
) -> Path:
    """
    HTML o'yinni Chromium'da ishga tushiradi,
    avtomatik o'ynaydi va MP4 video yaratadi.
    """

    _ensure_dirs()

    duration = max(3, min(duration, 60))

    raw_video = VIDEO_DIR / f"{slug}_raw.webm"
    mp4_path = VIDEO_DIR / f"{slug}.mp4"

    raw_video.unlink(missing_ok=True)
    mp4_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f"game_{slug}_"
    ) as temp_dir:

        html_file = Path(temp_dir) / f"{slug}.html"
        html_file.write_bytes(html_bytes)

        logger.info(
            "[GAME VIDEO] Starting: %s (%ss)",
            slug,
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
                    "--autoplay-policy=no-user-gesture-required",
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
                    html_file.as_uri(),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                await page.wait_for_timeout(1500)

                await _start_game(page)

                await _simulate_player(
                    page,
                    duration,
                )

                await page.wait_for_timeout(500)

            finally:
                await context.close()
                await browser.close()

    videos = sorted(
        VIDEO_DIR.glob("*.webm"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not videos:
        raise RuntimeError(
            "Video yozilmadi: Chromium WEBM yaratmadi."
        )

    recorded_video = videos[0]

    if recorded_video != raw_video:
        recorded_video.rename(raw_video)

    await _convert_to_mp4(
        raw_video,
        mp4_path,
    )

    raw_video.unlink(missing_ok=True)

    if not mp4_path.exists():
        raise RuntimeError(
            "MP4 yaratilmadi."
        )

    logger.info(
        "[GAME VIDEO] MP4 created: %s",
        mp4_path,
    )

    return mp4_path


async def _start_game(page) -> None:
    """
    O'yinning odatiy Start/Boshlash tugmalarini topib bosadi.
    """

    selectors = [
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

    for selector in selectors:
        try:
            target = page.locator(selector).first

            if await target.is_visible(timeout=500):
                await target.click()

                logger.info(
                    "[GAME VIDEO] Start clicked: %s",
                    selector,
                )

                await page.wait_for_timeout(500)
                return

        except Exception:
            continue


async def _simulate_player(
    page,
    duration: int,
) -> None:
    """
    Umumiy AI-o'yinchi harakatlari.

    Turli HTML o'yinlarda ishlashi uchun:
    - yurish
    - sakrash
    - otish
    - chap/o'ng
    - click/tap
    harakatlarini aralashtirib bajaradi.
    """

    end_time = (
        asyncio.get_running_loop().time()
        + duration
    )

    actions = [
        ("ArrowRight", 0.6),
        ("ArrowRight", 0.5),
        ("Space", 0.4),
        ("ArrowLeft", 0.5),
        ("ArrowRight", 0.7),
        ("ArrowUp", 0.4),
        ("Space", 0.4),
        ("ArrowRight", 0.6),
        ("Space", 0.3),
        ("ArrowLeft", 0.5),
    ]

    index = 0

    while (
        asyncio.get_running_loop().time()
        < end_time
    ):
        key, delay = actions[
            index % len(actions)
        ]

        index += 1

        try:
            await page.keyboard.press(key)
        except Exception:
            pass

        await _click_game_area(page)

        await page.wait_for_timeout(
            int(delay * 1000)
        )


async def _click_game_area(page) -> None:
    """
    Canvas yoki o'yin maydonining turli joylariga
    click/tap qiladi.
    """

    selectors = [
        "canvas",
        "#game",
        "#gameCanvas",
        ".game",
        ".game-container",
        "#app",
    ]

    for selector in selectors:
        try:
            target = page.locator(
                selector
            ).first

            if not await target.is_visible(
                timeout=100
            ):
                continue

            box = await target.bounding_box()

            if not box:
                continue

            points = [
                (0.25, 0.50),
                (0.50, 0.50),
                (0.75, 0.50),
                (0.50, 0.35),
                (0.50, 0.65),
            ]

            for px, py in points:
                x = box["x"] + box["width"] * px
                y = box["y"] + box["height"] * py

                try:
                    await page.mouse.click(x, y)
                except Exception:
                    pass

            return

        except Exception:
            continue


async def _convert_to_mp4(
    source: Path,
    destination: Path,
) -> None:
    """
    FFmpeg orqali WEBM → MP4.
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
        "[GAME VIDEO] Converting WEBM → MP4"
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode(
            "utf-8",
            errors="replace",
        )

        logger.error(
            "[GAME VIDEO] FFmpeg error: %s",
            error[-2000:],
        )

        raise RuntimeError(
            "FFmpeg MP4 conversion failed."
        )

    if not destination.exists():
        raise RuntimeError(
            "FFmpeg ishladi, ammo MP4 topilmadi."
        )