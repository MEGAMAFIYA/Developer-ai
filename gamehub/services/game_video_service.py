from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from playwright.async_api import (
    Page,
    async_playwright,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_DIR = (
    BASE_DIR
    / "webapp"
    / "generated_videos"
)

DEFAULT_DURATION = 12

VIEWPORT_WIDTH = 640
VIEWPORT_HEIGHT = 360


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTORIES
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    VIDEO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN MP4 GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

async def create_game_mp4(
    slug: str,
    html_bytes: bytes,
    duration: int = DEFAULT_DURATION,
) -> Path:
    """
    HTML o'yinni Chromium'da ishga tushiradi.

    Jarayon:
      1. HTML vaqtinchalik faylga yoziladi.
      2. Chromium ishga tushadi.
      3. O'yinning Start tugmasi avtomatik bosiladi.
      4. Start bosilgandan keyingina gameplay yoziladi.
      5. AI o'yinchi o'yinni faol boshqaradi.
      6. WEBM → MP4 aylantiriladi.
      7. Tayyor MP4 qaytariladi.
    """

    _ensure_dirs()

    duration = max(
        3,
        min(duration, 60),
    )

    raw_video = (
        VIDEO_DIR
        / f"{slug}_raw.webm"
    )

    mp4_path = (
        VIDEO_DIR
        / f"{slug}.mp4"
    )

    raw_video.unlink(
        missing_ok=True
    )

    mp4_path.unlink(
        missing_ok=True
    )

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

                # ─────────────────────────────────────────
                # LOAD GAME
                # ─────────────────────────────────────────

                await page.goto(
                    html_file.as_uri(),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                # Sahifa to'liq ishga tushishi uchun
                # juda qisqa kutish.
                await page.wait_for_timeout(
                    1000
                )

                # ─────────────────────────────────────────
                # START GAME
                # ─────────────────────────────────────────

                started = await _start_game(
                    page
                )

                if started:
                    logger.info(
                        "[GAME VIDEO] Game started successfully."
                    )

                    # Start bosilgandan keyin
                    # o'yin mexanikalari ishga tushishini
                    # kutamiz.
                    await page.wait_for_timeout(
                        700
                    )

                else:
                    logger.warning(
                        "[GAME VIDEO] "
                        "Start button not found. "
                        "Attempting gameplay anyway."
                    )

                    await page.wait_for_timeout(
                        300
                    )

                # ─────────────────────────────────────────
                # ACTIVE GAMEPLAY
                # ─────────────────────────────────────────

                await _simulate_player(
                    page,
                    duration,
                )

                # Oxirgi frame'lar yozilib ulgurishi
                # uchun juda qisqa kutish.
                await page.wait_for_timeout(
                    300
                )

            finally:

                # Video fayli context yopilganda
                # yakunlanadi.
                await context.close()

                await browser.close()

    # ─────────────────────────────────────────────────────────────────────────
    # FIND RECORDED VIDEO
    # ─────────────────────────────────────────────────────────────────────────

    videos = sorted(
        VIDEO_DIR.glob("*.webm"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not videos:
        raise RuntimeError(
            "Video yozilmadi: "
            "Chromium WEBM yaratmadi."
        )

    recorded_video = videos[0]

    if recorded_video != raw_video:

        raw_video.unlink(
            missing_ok=True
        )

        recorded_video.rename(
            raw_video
        )

    # ─────────────────────────────────────────────────────────────────────────
    # WEBM → MP4
    # ─────────────────────────────────────────────────────────────────────────

    await _convert_to_mp4(
        raw_video,
        mp4_path,
    )

    raw_video.unlink(
        missing_ok=True
    )

    if not mp4_path.exists():
        raise RuntimeError(
            "MP4 yaratilmadi."
        )

    logger.info(
        "[GAME VIDEO] MP4 created: %s",
        mp4_path,
    )

    return mp4_path


# ─────────────────────────────────────────────────────────────────────────────
# START BUTTON
# ─────────────────────────────────────────────────────────────────────────────

async def _start_game(
    page: Page,
) -> bool:
    """
    O'yinning Start/Boshlash tugmasini topadi
    va bosadi.

    True  → Start topildi va bosildi.
    False → Start topilmadi.
    """

    selectors = [
        # English
        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Play')",
        "button:has-text('PLAY')",

        # Uzbek
        "button:has-text('Boshlash')",
        "button:has-text('BOSHLASH')",
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

            if not await target.is_visible(
                timeout=250
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

        except Exception:
            continue

    # ─────────────────────────────────────────
    # TEXT-BASED FALLBACK
    # ─────────────────────────────────────────

    text_selectors = [
        "text=Start",
        "text=START",
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

            if not await target.is_visible(
                timeout=200
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
async def _start_game(page) -> bool:
    """
    Start/Boshlash tugmasini topadi va bosadi.
    Video yozish o'yin haqiqatan boshlanganidan keyin davom etadi.
    """

    selectors = [
        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Start Game')",
        "button:has-text('Boshlash')",
        "button:has-text('Boshlash!')",
        "button:has-text('O‘ynash')",
        "button:has-text(\"O'ynash\")",
        "#start",
        "#startButton",
        "#start-btn",
        ".start-button",
        ".start-btn",
        ".start-game",
        "[data-action='start']",
    ]

    for selector in selectors:
        try:
            target = page.locator(selector).first

            if await target.count() == 0:
                continue

            if await target.is_visible(timeout=300):
                await target.scroll_into_view_if_needed()
                await target.click(timeout=2000)

                logger.info(
                    "[GAME VIDEO] Start clicked: %s",
                    selector,
                )

                # O'yin ishga tushishi uchun juda qisqa kutish.
                await page.wait_for_timeout(300)

                return True

        except Exception as exc:
            logger.debug(
                "[GAME VIDEO] Start selector failed %s: %s",
                selector,
                exc,
            )

    # Agar Start tugmasi topilmasa, o'yin allaqachon
    # avtomatik boshlangan bo'lishi mumkin.
    logger.info(
        "[GAME VIDEO] No start button found; "
        "assuming game is already running."
    )

    return False


async def _simulate_player(
    page,
    duration: int,
) -> None:
    """
    Universal faol AI-o'yinchi.

    O'yin turidan qat'i nazar:
      - tez-tez harakat qiladi
      - chap/o'ng yuradi
      - sakraydi
      - Space bosadi
      - sichqoncha/tap ishlatadi
      - o'q otishga urinadi
      - xavfdan qochish uchun yo'nalishni almashtiradi

    Muhim:
    Bu universal boshqaruvchi bo'lgani uchun har bir HTML
    o'yinning ichki kodini o'zgartirmaydi.
    """

    loop = asyncio.get_running_loop()
    end_time = loop.time() + duration

    # Tez-tez takrorlanadigan tugmalar.
    movement_keys = [
        "ArrowRight",
        "ArrowRight",
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "Space",
        "ArrowLeft",
        "ArrowRight",
        "Space",
        "ArrowRight",
    ]

    index = 0

    while loop.time() < end_time:
        key = movement_keys[index % len(movement_keys)]
        index += 1

        try:
            await page.keyboard.down(key)
            await page.wait_for_timeout(120)
            await page.keyboard.up(key)
        except Exception:
            pass

        # Har bir siklda o'yin maydoniga faol click/tap.
        await _active_game_click(page)

        # Agar o'yinda standart o'q otish tugmalari bo'lsa,
        # vaqti-vaqti bilan ularni ham sinab ko'ramiz.
        if index % 2 == 0:
            for fire_key in ("Space", "KeyX", "KeyZ"):
                try:
                    await page.keyboard.press(fire_key)
                except Exception:
                    pass

        # Juda uzoq kutmaymiz — AI doim harakatda bo'ladi.
        await page.wait_for_timeout(180)


async def _active_game_click(page) -> None:
    """
    O'yin maydonini topib, faol tap/click qiladi.

    Canvas asosidagi o'yinlar uchun ayniqsa foydali.
    """

    selectors = [
        "canvas",
        "#game",
        "#gameCanvas",
        "#canvas",
        ".game",
        ".game-container",
        ".game-area",
        "#game-area",
        "#app",
        "body",
    ]

    for selector in selectors:
        try:
            target = page.locator(selector).first

            if await target.count() == 0:
                continue

            if not await target.is_visible(timeout=100):
                continue

            box = await target.bounding_box()

            if not box:
                continue

            # Markaz va atrofidagi nuqtalar.
            points = [
                (0.50, 0.50),
                (0.35, 0.50),
                (0.65, 0.50),
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