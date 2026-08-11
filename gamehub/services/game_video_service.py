from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

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

SESSION_DIR = (
    BASE_DIR
    / "webapp"
    / "video_sessions"
)

VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360

DEFAULT_DURATION = 12

MIN_DURATION = 3
MAX_DURATION = 60


# ============================================================
# DIRECTORY
# ============================================================

def _ensure_dirs() -> None:
    """
    Video va vaqtinchalik recording session
    papkalarini yaratadi.
    """

    VIDEO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SESSION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# VIDEO SESSION DATA
# ============================================================

class GameVideoSession:
    """
    Bitta o'yin uchun recording session.

    Session ichida:
    - HTML fayl
    - vaqtinchalik video papkasi
    - Playwright browser
    - browser context
    - page
    - recording holati
    saqlanadi.
    """

    def __init__(
        self,
        session_id: str,
        slug: str,
        html_path: Path,
        session_path: Path,
    ) -> None:

        self.session_id = session_id
        self.slug = slug

        self.html_path = html_path
        self.session_path = session_path

        self.video_dir = (
            session_path
            / "video"
        )

        self.video_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None

        self.recording_started = False
        self.recording_stopped = False

        self.webm_path: Path | None = None
        self.mp4_path: Path | None = None


# ============================================================
# CREATE SESSION
# ============================================================

async def create_recording_session(
    slug: str,
    html_bytes: bytes,
) -> GameVideoSession:
    """
    HTML o'yin uchun yangi recording session yaratadi.

    Muhim:
    Bu funksiya recordingni boshlamaydi.

    Faqat:
    - HTMLni vaqtinchalik saqlaydi
    - Chromiumni ochadi
    - o'yinni 640x360 oynada yuklaydi

    Recording keyin alohida boshlanadi.
    """

    _ensure_dirs()

    session_id = (
        f"{slug}_"
        f"{uuid.uuid4().hex[:12]}"
    )

    session_path = (
        SESSION_DIR
        / session_id
    )

    session_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    html_path = (
        session_path
        / f"{slug}.html"
    )

    html_path.write_bytes(
        html_bytes
    )

    session = GameVideoSession(
        session_id=session_id,
        slug=slug,
        html_path=html_path,
        session_path=session_path,
    )

    logger.info(
        "[GAME VIDEO] Creating session: %s",
        session_id,
    )

    try:
        from playwright.async_api import (
            async_playwright,
        )

        session.playwright = (
            await async_playwright().start()
        )

        session.browser = (
            await session.playwright.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
        )

        session.context = (
            await session.browser.new_context(
                viewport={
                    "width": VIDEO_WIDTH,
                    "height": VIDEO_HEIGHT,
                },
                device_scale_factor=1,
            )
        )

        session.page = (
            await session.context.new_page()
        )

        await session.page.goto(
            html_path.as_uri(),
            wait_until="domcontentloaded",
            timeout=30_000,
        )

        await session.page.wait_for_timeout(
            1_000
        )

        logger.info(
            "[GAME VIDEO] Game loaded: %s",
            session_id,
        )

        return session

    except Exception:

        await close_recording_session(
            session
        )

        raise


# ============================================================
# START GAME
# ============================================================

async def start_game_session(
    session: GameVideoSession,
) -> None:
    """
    O'yinning Start/Boshlash tugmasini topib bosishga urinadi.

    Bu recordingni boshlamaydi.
    """

    if not session.page:
        raise RuntimeError(
            "Game session hali tayyor emas."
        )

    selectors = [
        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Start Game')",
        "button:has-text('Play')",
        "button:has-text('PLAY')",
        "button:has-text('Boshlash')",
        "button:has-text('BOSHLASH')",
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
                session.page
                .locator(selector)
                .first
            )

            if await target.count() == 0:
                continue

            if not await target.is_visible(
                timeout=300
            ):
                continue

            await target.click(
                timeout=2_000
            )

            logger.info(
                "[GAME VIDEO] Game started: %s",
                selector,
            )

            await session.page.wait_for_timeout(
                300
            )

            return

        except Exception:
            continue

    logger.warning(
        "[GAME VIDEO] Start button not found."
    )


# ============================================================
# START RECORDING
# ============================================================

async def start_recording(
    session: GameVideoSession,
) -> None:
    """
    O'yin recordingini boshlaydi.

    Playwright video recording context
    yangi context bilan boshlanishi kerak,
    shuning uchun recording uchun page qayta
    yaratiladi.
    """

    if session.recording_started:
        raise RuntimeError(
            "Recording allaqachon boshlangan."
        )

    if not session.page:
        raise RuntimeError(
            "Game session mavjud emas."
        )

    # ========================================================
    # OLD PAGE
    # ========================================================

    try:
        await session.page.close()
    except Exception:
        pass

    # ========================================================
    # NEW RECORDING CONTEXT
    # ========================================================

    session.context = (
        await session.browser.new_context(
            viewport={
                "width": VIDEO_WIDTH,
                "height": VIDEO_HEIGHT,
            },
            device_scale_factor=1,
            record_video_dir=str(
                session.video_dir
            ),
            record_video_size={
                "width": VIDEO_WIDTH,
                "height": VIDEO_HEIGHT,
            },
        )
    )

    session.page = (
        await session.context.new_page()
    )

    await session.page.goto(
        session.html_path.as_uri(),
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    await session.page.wait_for_timeout(
        500
    )

    # Start tugmasini bosamiz.
    await start_game_session(
        session
    )

    session.recording_started = True
    session.recording_stopped = False

    logger.info(
        "[GAME VIDEO] Recording started: %s",
        session.session_id,
    )


# ============================================================
# STOP RECORDING
# ============================================================

async def stop_recording(
    session: GameVideoSession,
) -> Path:
    """
    Recordingni to'xtatadi va WEBM fayl yo'lini qaytaradi.
    """

    if not session.recording_started:
        raise RuntimeError(
            "Recording hali boshlanmagan."
        )

    if session.recording_stopped:
        if session.webm_path:
            return session.webm_path

        raise RuntimeError(
            "Recording allaqachon to'xtatilgan."
        )

    if not session.page:
        raise RuntimeError(
            "Recording page mavjud emas."
        )

    # Video obyektini oldindan olamiz.
    video = session.page.video

    # Contextni yopish recordingni yakunlaydi.
    await session.context.close()

    session.recording_stopped = True

    if video is None:
        raise RuntimeError(
            "Playwright video obyektini yaratmadi."
        )

    try:
        video_path = await video.path()
    except Exception as exc:
        raise RuntimeError(
            f"Recording faylini olishda xato: {exc}"
        ) from exc

    webm_path = Path(
        video_path
    )

    if not webm_path.exists():
        raise RuntimeError(
            "WEBM recording fayli topilmadi."
        )

    session.webm_path = webm_path

    logger.info(
        "[GAME VIDEO] Recording stopped: %s",
        webm_path,
    )

    return webm_path


# ============================================================
# CONVERT WEBM → MP4
# ============================================================

async def convert_recorded_video_to_mp4(
    source: Path,
    destination: Path,
) -> Path:
    """
    WEBM recordingni 640x360 MP4 ga aylantiradi.
    """

    _ensure_dirs()

    source = Path(source)
    destination = Path(destination)

    if not source.exists():
        raise FileNotFoundError(
            f"Video topilmadi: {source}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(source),

        "-vf",
        (
            "scale=640:360:"
            "force_original_aspect_ratio=decrease,"
            "pad=640:360:"
            "(ow-iw)/2:"
            "(oh-ih)/2"
        ),

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
        "[GAME VIDEO] Converting WEBM → MP4: %s",
        destination,
    )

    process = (
        await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    )

    _, stderr = (
        await process.communicate()
    )

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
            "WEBM → MP4 conversion failed."
        )

    if not destination.exists():
        raise RuntimeError(
            "MP4 yaratilmadi."
        )

    if destination.stat().st_size < 1024:
        raise RuntimeError(
            "MP4 fayl juda kichik yoki bo'sh."
        )

    logger.info(
        "[GAME VIDEO] MP4 created: %s",
        destination,
    )

    return destination


# ============================================================
# SAVE RECORDING
# ============================================================

async def save_recorded_video(
    slug: str,
    source: Path,
) -> Path:
    """
    Recordingni yakuniy:
        generated_videos/{slug}.mp4
    sifatida saqlaydi.
    """

    _ensure_dirs()

    mp4_path = (
        VIDEO_DIR
        / f"{slug}.mp4"
    )

    return await convert_recorded_video_to_mp4(
        source,
        mp4_path,
    )


# ============================================================
# FINISH SESSION
# ============================================================

async def finish_recording_session(
    session: GameVideoSession,
) -> Path:
    """
    Recordingni yakunlab, MP4 yaratadi.
    """

    if not session.webm_path:

        if session.recording_started:
            await stop_recording(
                session
            )

    if not session.webm_path:
        raise RuntimeError(
            "WEBM recording mavjud emas."
        )

    mp4_path = await save_recorded_video(
        session.slug,
        session.webm_path,
    )

    session.mp4_path = mp4_path

    logger.info(
        "[GAME VIDEO] Session finished: %s",
        session.session_id,
    )

    return mp4_path


# ============================================================
# CLOSE SESSION
# ============================================================

async def close_recording_session(
    session: GameVideoSession,
) -> None:
    """
    Browser va Playwright resurslarini xavfsiz yopadi.
    """

    try:
        if session.page:
            try:
                await session.page.close()
            except Exception:
                pass

        if session.context:
            try:
                await session.context.close()
            except Exception:
                pass

        if session.browser:
            try:
                await session.browser.close()
            except Exception:
                pass

        if session.playwright:
            try:
                await session.playwright.stop()
            except Exception:
                pass

    finally:
        session.page = None
        session.context = None
        session.browser = None
        session.playwright = None


# ============================================================
# CLEAN SESSION
# ============================================================

async def cleanup_recording_session(
    session: GameVideoSession,
) -> None:
    """
    Session tugagandan keyin vaqtinchalik
    fayllarni o'chiradi.

    Yakuniy MP4 generated_videos ichida qoladi.
    """

    await close_recording_session(
        session
    )

    try:
        shutil.rmtree(
            session.session_path,
            ignore_errors=True,
        )
    except Exception:
        pass

    logger.info(
        "[GAME VIDEO] Session cleaned: %s",
        session.session_id,
    )


# ============================================================
# VIDEO PATH
# ============================================================

def get_video_path(
    slug: str,
) -> Path:
    """
    Tayyor MP4 fayl manzilini qaytaradi.
    """

    _ensure_dirs()

    return (
        VIDEO_DIR
        / f"{slug}.mp4"
    )