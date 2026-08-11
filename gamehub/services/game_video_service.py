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


# ============================================================
# SETTINGS
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

    _ensure_dirs()

    duration = max(
        MIN_DURATION,
        min(int(duration), MAX_DURATION),
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

                # ====================================================
                # LOAD GAME
                # ====================================================

                await page.goto(
                    html_file.as_uri(),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                await page.wait_for_timeout(
                    500
                )

                # ====================================================
                # START GAME
                # ====================================================

                started = await _start_game(
                    page
                )

                if started:

                    logger.info(
                        "[GAME VIDEO] "
                        "Game started successfully."
                    )

                    await page.wait_for_timeout(
                        250
                    )

                else:

                    logger.warning(
                        "[GAME VIDEO] "
                        "Start button not found."
                    )

                    await page.wait_for_timeout(
                        250
                    )

                # ====================================================
                # ACTIVE GAMEPLAY
                # ====================================================

                await _simulate_player(
                    page,
                    duration,
                )

                await page.wait_for_timeout(
                    250
                )

            finally:

                try:
                    await context.close()
                finally:
                    await browser.close()

    # ============================================================
    # FIND RECORDED WEBM
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
    # CONVERT TO MP4
    # ============================================================

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


# ============================================================
# START BUTTON
# ============================================================

async def _start_game(
    page: Page,
) -> bool:

    selectors = [

        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Start Game')",

        "button:has-text('Play')",
        "button:has-text('PLAY')",

        "button:has-text('Boshlash')",
        "button:has-text('BOSHLASH')",
        "button:has-text('Boshlash!')",

        "button:has-text('O‘ynash')",
        "button:has-text(\"O'ynash\")",
        "button:has-text('OYNASH')",

        "#start",
        "#startButton",
        "#start-btn",
        "#startGame",
        "#start-game",

        "#play",
        "#playButton",
        "#play-btn",
        "#playGame",

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

            target = (
                page
                .locator(selector)
                .first
            )

            if await target.count() == 0:
                continue

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
                timeout=2000
            )

            logger.info(
                "[GAME VIDEO] Start clicked: %s",
                selector,
            )

            await page.wait_for_timeout(
                300
            )

            return True

        except Exception as exc:

            logger.debug(
                "[GAME VIDEO] "
                "Start selector failed %s: %s",
                selector,
                exc,
            )

    # Text fallback

    text_selectors = [
        "text=Start",
        "text=START",
        "text=Start Game",
        "text=Play",
        "text=PLAY",
        "text=Boshlash",
        "text=BOSHLASH",
        "text=Boshlash!",
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
                timeout=200
            ):
                continue

            await target.click(
                timeout=1500
            )

            logger.info(
                "[GAME VIDEO] "
                "Fallback start clicked: %s",
                selector,
            )

            await page.wait_for_timeout(
                300
            )

            return True

        except Exception:
            continue

    logger.warning(
        "[GAME VIDEO] Start button not found."
    )

    return False

# ============================================================
# AI GAMEPLAY
# ============================================================

async def _simulate_player(
    page: Page,
    duration: int,
) -> None:
    """
    Universal faol AI o'yinchi.

    O'yin ichini kuzatishga urinadi:
    - dushman/xavfni aniqlaydi
    - dushman bo'lsa hujum qiladi
    - xavf yaqin bo'lsa qochadi
    - oddiy holatda faol harakat qiladi
    - sakrash va hujum tugmalarini sinaydi
    - mouse/tap orqali ham boshqaradi
    """

    loop = asyncio.get_running_loop()

    end_time = (
        loop.time()
        + duration
    )

    index = 0

    while loop.time() < end_time:

        # ====================================================
        # O'YIN HOLATINI TEKSHIRISH
        # ====================================================

        threat = await _detect_threat(
            page
        )

        # ====================================================
        # XAVF JUDA YAQIN
        # ====================================================

        if threat == "danger":

            logger.debug(
                "[GAME VIDEO] Danger detected"
            )

            # Tez qochish
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

            # Sakrashga urinadi
            await _press_key(
                page,
                "ArrowUp",
                160,
            )

            await _press_key(
                page,
                "Space",
                120,
            )

        # ====================================================
        # DUSHMAN
        # ====================================================

        elif threat == "enemy":

            logger.debug(
                "[GAME VIDEO] Enemy detected"
            )

            # Ketma-ket o'q otish
            await _fire(
                page
            )

            await page.wait_for_timeout(
                100
            )

            await _fire(
                page
            )

            # Dushmandan masofa olish
            await _press_key(
                page,
                "ArrowRight",
                180,
            )

        # ====================================================
        # ODDIY GAMEPLAY
        # ====================================================

        else:

            movement = [
                ("ArrowRight", 220),
                ("ArrowRight", 180),
                ("ArrowLeft", 160),
                ("ArrowRight", 240),
                ("ArrowUp", 160),
                ("ArrowRight", 200),
                ("Space", 140),
                ("ArrowLeft", 180),
                ("ArrowRight", 260),
                ("ArrowUp", 130),
            ]

            key, hold_time = (
                movement[
                    index
                    % len(movement)
                ]
            )

            await _press_key(
                page,
                key,
                hold_time,
            )

        index += 1

        # ====================================================
        # TEZ-TEZ HUJUM
        # ====================================================

        if index % 2 == 0:

            await _fire(
                page
            )

        # ====================================================
        # MOUSE / TAP
        # ====================================================

        if index % 2 == 0:

            await _active_game_click(
                page
            )

        # Juda uzoq kutmaymiz.
        await page.wait_for_timeout(
            80
        )


# ============================================================
# KEY PRESS
# ============================================================

async def _press_key(
    page: Page,
    key: str,
    duration_ms: int,
) -> None:
    """
    Tugmani qisqa vaqt bosib turadi.
    """

    try:

        await page.keyboard.down(
            key
        )

        await page.wait_for_timeout(
            duration_ms
        )

        await page.keyboard.up(
            key
        )

    except Exception:

        try:
            await page.keyboard.up(
                key
            )
        except Exception:
            pass


# ============================================================
# FIRE / ATTACK
# ============================================================

async def _fire(
    page: Page,
) -> None:
    """
    Universal hujum tizimi.

    Turli o'yinlarda ishlashi uchun:
    Space, X, Z, Control va mouse
    orqali hujum qilishga urinadi.
    """

    fire_keys = [
        "Space",
        "KeyX",
        "KeyZ",
        "Control",
    ]

    for key in fire_keys:

        try:

            await page.keyboard.press(
                key
            )

        except Exception:
            pass

        await page.wait_for_timeout(
            25
        )

    # Mouse/tap orqali ham sinab ko'ramiz.
    await _active_game_click(
        page
    )


# ============================================================
# ACTIVE GAME CLICK
# ============================================================

async def _active_game_click(
    page: Page,
) -> None:
    """
    O'yin maydonini topib,
    turli nuqtalariga click/tap qiladi.

    Canvas o'yinlari uchun foydali.
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
                timeout=100
            ):
                continue

            box = await target.bounding_box()

            if not box:
                continue

            points = [

                # Markaz
                (0.50, 0.50),

                # Chap
                (0.30, 0.50),

                # O'ng
                (0.70, 0.50),

                # Yuqori
                (0.50, 0.35),

                # Past
                (0.50, 0.65),
            ]

            for px, py in points:

                x = (
                    box["x"]
                    + box["width"] * px
                )

                y = (
                    box["y"]
                    + box["height"] * py
                )

                try:

                    await page.mouse.click(
                        x,
                        y,
                    )

                except Exception:
                    pass

            return

        except Exception:
            continue


# ============================================================
# SCREEN / GAME STATE ANALYSIS
# ============================================================

async def _detect_threat(
    page: Page,
) -> str:
    """
    O'yin ichidagi dushman/xavfni aniqlashga urinadi.

    Natija:

        "danger"
        "enemy"
        "none"

    Bu universal tizim bo'lgani uchun
    turli HTML o'yinlarning DOM elementlari,
    canvas va matnlarini tekshiradi.
    """

    # ========================================================
    # 1. DOM MATNLARINI TEKSHIRISH
    # ========================================================

    try:

        text = await page.locator(
            "body"
        ).inner_text(
            timeout=300
        )

        text_lower = (
            text.lower()
        )

    except Exception:

        text_lower = ""

    # ========================================================
    # DUSHMAN / XAVF SO'ZLARI
    # ========================================================

    danger_words = [
        "enemy",
        "dushman",
        "zombie",
        "zombi",
        "police",
        "politsiya",
        "monster",
        "maxluq",
        "danger",
        "xavf",
        "attack",
        "hujum",
        "chase",
        "quvish",
        "obstacle",
        "to'siq",
        "tosiq",
        "game over",
    ]

    enemy_words = [
        "enemy",
        "dushman",
        "zombie",
        "zombi",
        "monster",
        "police",
        "politsiya",
    ]

    # ========================================================
    # XAVFNI ANIQLASH
    # ========================================================

    for word in danger_words:

        if word in text_lower:

            # Game Over ham xavf sifatida
            # qaytariladi, lekin AI baribir
            # harakatni davom ettiradi.

            if (
                "game over"
                not in text_lower
            ):

                return "danger"

    # ========================================================
    # DUSHMAN ANIQLASH
    # ========================================================

    for word in enemy_words:

        if word in text_lower:

            return "enemy"

    # ========================================================
    # DOM CLASS / ID TEKSHIRISH
    # ========================================================

    try:

        elements = await page.locator(
            "[class], [id]"
        ).all()

        checked = 0

        for element in elements:

            if checked >= 100:
                break

            checked += 1

            try:

                class_name = (
                    await element.get_attribute(
                        "class"
                    )
                    or ""
                )

                element_id = (
                    await element.get_attribute(
                        "id"
                    )
                    or ""
                )

                value = (
                    f"{class_name} "
                    f"{element_id}"
                ).lower()

                for word in enemy_words:

                    if word in value:

                        return "enemy"

            except Exception:
                continue

    except Exception:
        pass

    return "none"

# ============================================================
# VIDEO CONVERSION
# ============================================================

async def _convert_to_mp4(
    source: Path,
    destination: Path,
) -> None:
    """
    WEBM → MP4.

    FFmpeg yordamida Chromium yozgan
    WEBM videoni Telegram uchun MP4 ga
    aylantiradi.
    """

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(source),

        # Video codec
        "-c:v",
        "libx264",

        # Tezroq render
        "-preset",
        "veryfast",

        # Telegram va mobil qurilmalar
        # bilan yaxshi moslik
        "-pix_fmt",
        "yuv420p",

        # MP4 tez ochilishi uchun
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

    # ========================================================
    # FFMPEG ERROR
    # ========================================================

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

    # ========================================================
    # FILE CHECK
    # ========================================================

    if not destination.exists():

        raise RuntimeError(
            "FFmpeg ishladi, ammo MP4 topilmadi."
        )

    # Juda kichik faylni noto'g'ri video
    # deb hisoblaymiz.
    if destination.stat().st_size < 1024:

        raise RuntimeError(
            "MP4 fayl juda kichik yoki bo'sh."
        )

    logger.info(
        "[GAME VIDEO] Conversion complete: %s",
        destination,
    )