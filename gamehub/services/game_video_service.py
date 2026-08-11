from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Page,
    async_playwright,
)

logger = logging.getLogger(__name__)


# ============================================================
# PATHS / SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_DIR = (
    BASE_DIR
    / "webapp"
    / "generated_videos"
)

DEFAULT_DURATION = 12

VIEWPORT_WIDTH = 640
VIEWPORT_HEIGHT = 360

MIN_DURATION = 3
MAX_DURATION = 60


# ============================================================
# DIRECTORY
# ============================================================

def _ensure_dirs() -> None:
    VIDEO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# MAIN MP4 GENERATOR
# ============================================================

async def create_game_mp4(
    slug: str,
    html_bytes: bytes,
    duration: int = DEFAULT_DURATION,
) -> Path:
    """
    HTML o'yinni Chromium orqali ishga tushiradi.

    Jarayon:

    1. HTML vaqtinchalik faylga yoziladi.
    2. Chromium ishga tushadi.
    3. O'yin sahifasi ochiladi.
    4. Start/Boshlash tugmasi topiladi va bosiladi.
    5. Start bosilgandan keyin gameplay boshlanadi.
    6. AI o'yinchi faol harakat qiladi.
    7. O'yin maydoni kuzatiladi.
    8. WEBM yozuv MP4 ga aylantiriladi.
    9. Tayyor MP4 qaytariladi.

    Muhim:
    Playwright video yozuvi context yaratilgan
    paytdan boshlab olinadi. Lekin yakuniy MP4
    faqat Start bosilgandan keyingi gameplay
    qismidan olinadi.
    """

    _ensure_dirs()

    duration = max(
        MIN_DURATION,
        min(
            int(duration),
            MAX_DURATION,
        ),
    )

    raw_video = (
        VIDEO_DIR
        / f"{slug}_raw.webm"
    )

    mp4_path = (
        VIDEO_DIR
        / f"{slug}.mp4"
    )

    # Eski fayllarni o'chirish.
    raw_video.unlink(
        missing_ok=True
    )

    mp4_path.unlink(
        missing_ok=True
    )

    # Eski WEBM fayllar aralashib ketmasligi uchun
    # vaqt belgisi bilan ishlaymiz.
    created_before = time.time()

    with tempfile.TemporaryDirectory(
        prefix=f"game_{slug}_"
    ) as temp_dir:

        html_file = (
            Path(temp_dir)
            / f"{slug}.html"
        )

        html_file.write_bytes(
            html_bytes
        )

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
                    "width": VIEWPORT_WIDTH,
                    "height": VIEWPORT_HEIGHT,
                },
                device_scale_factor=1,
                record_video_dir=str(
                    VIDEO_DIR
                ),
                record_video_size={
                    "width": VIEWPORT_WIDTH,
                    "height": VIEWPORT_HEIGHT,
                },
            )

            page = await context.new_page()

            try:

                # ------------------------------------------------
                # LOAD HTML
                # ------------------------------------------------

                await page.goto(
                    html_file.as_uri(),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                # Sahifa JS/CSS ishga tushishi uchun
                # qisqa kutish.
                await page.wait_for_timeout(
                    500
                )

                # ------------------------------------------------
                # START GAME
                # ------------------------------------------------

                started = await _start_game(
                    page
                )

                if started:

                    logger.info(
                        "[GAME VIDEO] "
                        "Game started successfully."
                    )

                    # Start click'dan keyin game loop
                    # ishga tushishi uchun juda qisqa vaqt.
                    await page.wait_for_timeout(
                        250
                    )

                else:

                    logger.warning(
                        "[GAME VIDEO] "
                        "Start button not found. "
                        "Checking whether game is already running."
                    )

                    # Auto-start o'yinlar uchun.
                    await page.wait_for_timeout(
                        250
                    )

                # ------------------------------------------------
                # ACTIVE GAMEPLAY
                # ------------------------------------------------

                await _simulate_player(
                    page,
                    duration,
                )

                # Oxirgi frame'larni yozib olish.
                await page.wait_for_timeout(
                    250
                )

            finally:

                # Context yopilganda Playwright video
                # faylni yakunlaydi.
                try:
                    await context.close()
                finally:
                    await browser.close()

    # ============================================================
    # FIND NEW WEBM
    # ============================================================

    videos = [
        path
        for path in VIDEO_DIR.glob("*.webm")
        if path.stat().st_mtime >= created_before
    ]

    videos.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not videos:
        raise RuntimeError(
            "Video yozilmadi: Chromium WEBM yaratmadi."
        )

    recorded_video = videos[0]

    # Biz kutgan raw nomga o'tkazish.
    if recorded_video != raw_video:

        raw_video.unlink(
            missing_ok=True
        )

        recorded_video.rename(
            raw_video
        )

    logger.info(
        "[GAME VIDEO] WEBM recorded: %s",
        raw_video,
    )


# ============================================================
# START BUTTON
# ============================================================

async def _start_game(
    page: Page,
) -> bool:
    """
    O'yinning Start/Boshlash/O'ynash tugmasini topadi.

    True:
        tugma topildi va bosildi.

    False:
        tugma topilmadi.
    """

    selectors = [
        # English
        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Start Game')",
        "button:has-text('PLAY')",
        "button:has-text('Play')",

        # Uzbek
        "button:has-text('Boshlash')",
        "button:has-text('BOSHLASH')",
        "button:has-text('Boshlash!')",
        "button:has-text('O‘ynash')",
        "button:has-text(\"O'ynash\")",
        "button:has-text('OYNASH')",

        # Common IDs
        "#start",
        "#startButton",
        "#start-btn",
        "#startGame",
        "#start-game",

        "#play",
        "#playButton",
        "#play-btn",
        "#playGame",

        # Common classes
        ".start-button",
        ".start-btn",
        ".start-game",

        ".play-button",
        ".play-btn",
        ".play-game",

        # Data attributes
        "[data-action='start']",
        "[data-action='play']",
        "[data-action='start-game']",
        "[data-action='play-game']",
    ]

    for selector in selectors:

        try:

            target = (
                page
                .locator(selector)
                .first
            )

            if await target.count() == 0:
                continue

            if not await target.is_visible(
                timeout=200
            ):
                continue

            try:
                await target.scroll_into_view_if_needed(
                    timeout=500
                )
            except Exception:
                pass

            await target.click(
                timeout=1500
            )

            logger.info(
                "[GAME VIDEO] Start clicked: %s",
                selector,
            )

            return True

        except Exception as exc:

            logger.debug(
                "[GAME VIDEO] "
                "Start selector failed %s: %s",
                selector,
                exc,
            )

            continue

    # Text fallback.
    text_selectors = [
        "text=Start",
        "text=START",
        "text=Start Game",
        "text=Play",
        "text=PLAY",
        "text=Boshlash",
        "text=BOSHLASH",
        "text=O‘ynash",
        "text=O'ynash",
    ]

    for selector in text_selectors:

        try:

            target = (
                page
                .locator(selector)
                .first
            )

            if await target.count() == 0:
                continue

            if not await target.is_visible(
                timeout=150
            ):
                continue

            await target.click(
                timeout=1000
            )

            logger.info(
                "[GAME VIDEO] "
                "Fallback start clicked: %s",
                selector,
            )

            return True

        except Exception:
            continue

    return False
async def _start_game(page: Page) -> bool:
    """
    Start/Boshlash tugmasini topadi va bosadi.
    """

    selectors = [
        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Start Game')",
        "button:has-text('PLAY')",
        "button:has-text('Play')",
        "button:has-text('Boshlash')",
        "button:has-text('Boshlash!')",
        "button:has-text('O‘ynash')",
        "button:has-text(\"O'ynash\")",
        "#start",
        "#startButton",
        "#start-btn",
        "#startGame",
        "#start-game",
        "#play",
        "#playButton",
        "#play-btn",
        ".start-button",
        ".start-btn",
        ".start-game",
        ".play-button",
        ".play-btn",
        ".play-game",
        "[data-action='start']",
        "[data-action='play']",
        "[data-action='start-game']",
        "[data-action='play-game']",
    ]

    for selector in selectors:
        try:
            target = page.locator(selector).first

            if await target.count() == 0:
                continue

            if not await target.is_visible(timeout=250):
                continue

            try:
                await target.scroll_into_view_if_needed(
                    timeout=500
                )
            except Exception:
                pass

            await target.click(timeout=2000)

            logger.info(
                "[GAME VIDEO] Start clicked: %s",
                selector,
            )

            await page.wait_for_timeout(300)

            return True

        except Exception as exc:
            logger.debug(
                "[GAME VIDEO] Start selector failed %s: %s",
                selector,
                exc,
            )

    # Matn orqali qo'shimcha qidirish
    text_selectors = [
        "text=Start",
        "text=START",
        "text=Start Game",
        "text=Play",
        "text=PLAY",
        "text=Boshlash",
        "text=Boshlash!",
        "text=O‘ynash",
        "text=O'ynash",
    ]

    for selector in text_selectors:
        try:
            target = page.locator(selector).first

            if await target.count() == 0:
                continue

            if not await target.is_visible(timeout=200):
                continue

            await target.click(timeout=1500)

            logger.info(
                "[GAME VIDEO] Fallback start clicked: %s",
                selector,
            )

            await page.wait_for_timeout(300)

            return True

        except Exception:
            continue

    logger.warning(
        "[GAME VIDEO] Start button not found."
    )

    return False


async def _simulate_player(
    page: Page,
    duration: int,
) -> None:
    """
    Universal faol AI o'yinchi.

    AI:
    - doimiy yuradi
    - yo'nalishni tez-tez almashtiradi
    - sakraydi
    - Space/X/Z orqali hujum qiladi
    - mouse/tap ishlatadi
    - xavfdan qochishga urinadi
    - ekrandagi dushman/obyektlarni aniqlashga urinadi
    """

    loop = asyncio.get_running_loop()
    end_time = loop.time() + duration

    index = 0

    while loop.time() < end_time:

        # ─────────────────────────────────────────────
        # 1. EKRANDAGI O'YIN HOLATINI TEKSHIRISH
        # ─────────────────────────────────────────────

        threat = await _detect_threat(page)

        if threat == "danger":
            # Dushman yoki xavf yaqin bo'lsa:
            # yo'nalishni tez o'zgartirib qochamiz.
            await _press_key(
                page,
                "ArrowLeft",
                180,
            )

            await _press_key(
                page,
                "ArrowRight",
                220,
            )

            await _press_key(
                page,
                "ArrowUp",
                180,
            )

        elif threat == "enemy":
            # Dushman ko'rinsa:
            # tez-tez o'q otishga urinadi.
            await _fire(page)

            await _press_key(
                page,
                "ArrowRight",
                180,
            )

            await _fire(page)

        else:
            # Oddiy gameplay.
            movement = [
                ("ArrowRight", 220),
                ("ArrowRight", 180),
                ("ArrowLeft", 160),
                ("ArrowRight", 240),
                ("ArrowUp", 160),
                ("ArrowRight", 200),
                ("Space", 140),
                ("ArrowLeft", 180),
            ]

            key, hold_time = movement[
                index % len(movement)
            ]

            await _press_key(
                page,
                key,
                hold_time,
            )

        index += 1

        # Har bir siklda hujumni ham sinab ko'ramiz.
        if index % 2 == 0:
            await _fire(page)

        # O'yin maydoniga tap/click.
        await _active_game_click(page)

        # Juda uzoq kutmaymiz.
        await page.wait_for_timeout(80)


async def _press_key(
    page: Page,
    key: str,
    duration_ms: int,
) -> None:
    """
    Tugmani qisqa vaqt bosib turadi.
    """

    try:
        await page.keyboard.down(key)

        await page.wait_for_timeout(
            duration_ms
        )

        await page.keyboard.up(key)

    except Exception:
        try:
            await page.keyboard.up(key)
        except Exception:
            pass


async def _fire(page: Page) -> None:
    """
    Universal hujum/o'q otish.

    Turli o'yinlarda ishlashi uchun
    bir nechta standart tugmalar sinab ko'riladi.
    """

    fire_keys = [
        "Space",
        "KeyX",
        "KeyZ",
        "Control",
    ]

    for key in fire_keys:
        try:
            await page.keyboard.press(key)
        except Exception:
            pass

    # Mouse orqali ham hujum/tap.
    await _active_game_click(page)
async def _convert_to_mp4(
    source: Path,
    destination: Path,
) -> None:
    """
    WEBM → MP4.
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
            error[-3000:],
        )

        raise RuntimeError(
            "FFmpeg MP4 conversion failed."
        )

    if not destination.exists():
        raise RuntimeError(
            "FFmpeg ishladi, ammo MP4 topilmadi."
        )

    if destination.stat().st_size < 1024:
        raise RuntimeError(
            "MP4 fayl juda kichik yoki bo'sh."
        )

    logger.info(
        "[GAME VIDEO] Conversion complete: %s",
        destination,
    )