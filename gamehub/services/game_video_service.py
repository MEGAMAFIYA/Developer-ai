from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import (
    Page,
    Browser,
    BrowserContext,
    async_playwright,
)

logger = logging.getLogger(__name__)


# ============================================================================
# PATHS / SETTINGS
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_DIR = (
    BASE_DIR
    / "webapp"
    / "generated_videos"
)

DEFAULT_DURATION = 12

VIEWPORT_WIDTH = 640
VIEWPORT_HEIGHT = 360

CHROMIUM_PATH = "/usr/bin/chromium"

MIN_DURATION = 3
MAX_DURATION = 60


# ============================================================================
# AI SETTINGS
# ============================================================================

# Dushman shu masofadan uzoq bo'lsa oddiy harakat qilinadi.
ENEMY_FAR_DISTANCE = 260

# Shu masofada dushmanga qarab otishga uriniladi.
ENEMY_ATTACK_DISTANCE = 180

# Shu masofadan yaqin dushman xavfli deb hisoblanadi.
ENEMY_DANGER_DISTANCE = 85

# AI qarorlarini qanchalik tez yangilaydi.
AI_TICK_MS = 180

# Harakat tugmasini qancha vaqt ushlab turadi.
KEY_HOLD_MS = 120


# ============================================================================
# DIRECTORIES
# ============================================================================

def _ensure_dirs() -> None:
    VIDEO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================================
# UTILITY
# ============================================================================

def _clamp_duration(duration: int) -> int:
    try:
        duration = int(duration)
    except Exception:
        duration = DEFAULT_DURATION

    return max(
        MIN_DURATION,
        min(duration, MAX_DURATION),
    )


def _distance(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    return math.sqrt(
        ((x2 - x1) ** 2)
        + ((y2 - y1) ** 2)
    )


def _safe_number(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        number = float(value)

        if math.isfinite(number):
            return number

    except Exception:
        pass

    return None


def _extract_xy(
    value: Any,
) -> Optional[tuple[float, float]]:
    """
    Turli xil JS obyektlardan x/y koordinatalarni topishga urinadi.
    """

    if not isinstance(value, dict):
        return None

    x_keys = (
        "x",
        "X",
        "left",
        "posX",
        "positionX",
    )

    y_keys = (
        "y",
        "Y",
        "top",
        "posY",
        "positionY",
    )

    x = None
    y = None

    for key in x_keys:
        if key in value:
            x = _safe_number(value.get(key))
            if x is not None:
                break

    for key in y_keys:
        if key in value:
            y = _safe_number(value.get(key))
            if y is not None:
                break

    if x is None or y is None:
        position = value.get("position")

        if isinstance(position, dict):
            x = (
                _safe_number(position.get("x"))
                if x is None
                else x
            )

            y = (
                _safe_number(position.get("y"))
                if y is None
                else y
            )

    if x is None or y is None:
        return None

    return (
        x,
        y,
    )


# ============================================================================
# JAVASCRIPT GAME INSPECTOR
# ============================================================================

GAME_INSPECTOR_JS = r"""
() => {
    const result = {
        player: null,
        enemies: [],
        obstacles: [],
        bullets: [],
        coins: [],
        candidates: []
    };

    const lower = (value) =>
        String(value || "").toLowerCase();

    const looksLikePosition = (obj) => {
        if (!obj || typeof obj !== "object") {
            return false;
        }

        const hasX =
            typeof obj.x === "number" ||
            typeof obj.X === "number" ||
            typeof obj.left === "number" ||
            typeof obj.posX === "number";

        const hasY =
            typeof obj.y === "number" ||
            typeof obj.Y === "number" ||
            typeof obj.top === "number" ||
            typeof obj.posY === "number";

        return hasX && hasY;
    };

    const normalizeObject = (
        obj,
        source,
        name
    ) => {
        if (!obj || typeof obj !== "object") {
            return null;
        }

        let x = null;
        let y = null;

        if (typeof obj.x === "number") {
            x = obj.x;
        } else if (typeof obj.X === "number") {
            x = obj.X;
        } else if (typeof obj.left === "number") {
            x = obj.left;
        } else if (typeof obj.posX === "number") {
            x = obj.posX;
        } else if (
            obj.position &&
            typeof obj.position.x === "number"
        ) {
            x = obj.position.x;
        }

        if (typeof obj.y === "number") {
            y = obj.y;
        } else if (typeof obj.Y === "number") {
            y = obj.Y;
        } else if (typeof obj.top === "number") {
            y = obj.top;
        } else if (typeof obj.posY === "number") {
            y = obj.posY;
        } else if (
            obj.position &&
            typeof obj.position.y === "number"
        ) {
            y = obj.position.y;
        }

        if (
            typeof x !== "number" ||
            typeof y !== "number"
        ) {
            return null;
        }

        return {
            x,
            y,
            source,
            name
        };
    };

    const inspectValue = (
        value,
        key,
        depth
    ) => {
        if (depth > 2) {
            return;
        }

        if (!value) {
            return;
        }

        const keyLower = lower(key);

        // ------------------------------------------------------------
        // Direct object
        // ------------------------------------------------------------

        if (
            typeof value === "object" &&
            !Array.isArray(value)
        ) {
            const normalized =
                normalizeObject(
                    value,
                    "window",
                    key
                );

            if (normalized) {
                result.candidates.push(
                    normalized
                );

                if (
                    keyLower.includes("player") ||
                    keyLower.includes("hero") ||
                    keyLower.includes("character")
                ) {
                    if (!result.player) {
                        result.player =
                            normalized;
                    }
                }

                if (
                    keyLower.includes("enemy") ||
                    keyLower.includes("enemies") ||
                    keyLower.includes("monster") ||
                    keyLower.includes("zombie") ||
                    keyLower.includes("opponent")
                ) {
                    result.enemies.push(
                        normalized
                    );
                }

                if (
                    keyLower.includes("obstacle") ||
                    keyLower.includes("barrier") ||
                    keyLower.includes("trap")
                ) {
                    result.obstacles.push(
                        normalized
                    );
                }

                if (
                    keyLower.includes("bullet") ||
                    keyLower.includes("projectile") ||
                    keyLower.includes("shot")
                ) {
                    result.bullets.push(
                        normalized
                    );
                }

                if (
                    keyLower.includes("coin") ||
                    keyLower.includes("collect")
                ) {
                    result.coins.push(
                        normalized
                    );
                }
            }

            // Search one level deeper.
            for (
                const nestedKey of Object.keys(value).slice(0, 40)
            ) {
                try {
                    const nested =
                        value[nestedKey];

                    if (
                        nested &&
                        typeof nested === "object"
                    ) {
                        inspectValue(
                            nested,
                            `${key}.${nestedKey}`,
                            depth + 1
                        );
                    }
                } catch (_) {}
            }

            return;
        }

        // ------------------------------------------------------------
        // Array
        // ------------------------------------------------------------

        if (Array.isArray(value)) {
            const max =
                Math.min(
                    value.length,
                    50
                );

            for (
                let i = 0;
                i < max;
                i++
            ) {
                try {
                    inspectValue(
                        value[i],
                        `${key}[${i}]`,
                        depth + 1
                    );
                } catch (_) {}
            }
        }
    };

    // ----------------------------------------------------------------
    // Search common global game variables.
    // ----------------------------------------------------------------

    const keys = Object.keys(window);

    const priority = [];

    const normal = [];

    for (const key of keys) {
        const name = lower(key);

        if (
            name.includes("player") ||
            name.includes("enemy") ||
            name.includes("enemies") ||
            name.includes("monster") ||
            name.includes("zombie") ||
            name.includes("obstacle") ||
            name.includes("bullet") ||
            name.includes("projectile") ||
            name.includes("game")
        ) {
            priority.push(key);
        } else {
            normal.push(key);
        }
    }

    const ordered =
        priority.concat(normal);

    for (
        const key of ordered.slice(0, 180)
    ) {
        try {
            inspectValue(
                window[key],
                key,
                0
            );
        } catch (_) {}
    }

    // ----------------------------------------------------------------
    // DOM based fallback.
    // ----------------------------------------------------------------

    const elements =
        Array.from(
            document.querySelectorAll(
                "[id], [class]"
            )
        ).slice(0, 300);

    for (const element of elements) {
        try {
            const name =
                `${element.id || ""} ${
                    typeof element.className === "string"
                        ? element.className
                        : ""
                }`;

            const nameLower =
                lower(name);

            const rect =
                element.getBoundingClientRect();

            if (
                rect.width <= 0 ||
                rect.height <= 0
            ) {
                continue;
            }

            const object = {
                x:
                    rect.left +
                    rect.width / 2,
                y:
                    rect.top +
                    rect.height / 2,
                source: "dom",
                name
            };

            if (
                nameLower.includes("player") ||
                nameLower.includes("hero") ||
                nameLower.includes("character")
            ) {
                if (!result.player) {
                    result.player =
                        object;
                }
            }

            if (
                nameLower.includes("enemy") ||
                nameLower.includes("monster") ||
                nameLower.includes("zombie") ||
                nameLower.includes("opponent")
            ) {
                result.enemies.push(
                    object
                );
            }

            if (
                nameLower.includes("obstacle") ||
                nameLower.includes("barrier") ||
                nameLower.includes("trap")
            ) {
                result.obstacles.push(
                    object
                );
            }

        } catch (_) {}
    }

    // ----------------------------------------------------------------
    // Remove obvious duplicates.
    // ----------------------------------------------------------------

    const unique = (items) => {
        const output = [];
        const seen = new Set();

        for (const item of items) {
            if (!item) {
                continue;
            }

            const signature =
                `${Math.round(item.x)}:` +
                `${Math.round(item.y)}:` +
                `${item.name}`;

            if (seen.has(signature)) {
                continue;
            }

            seen.add(signature);
            output.push(item);
        }

        return output;
    };

    result.enemies =
        unique(result.enemies);

    result.obstacles =
        unique(result.obstacles);

    result.bullets =
        unique(result.bullets);

    result.coins =
        unique(result.coins);

    result.candidates =
        unique(result.candidates);

    return result;
}
"""


# ============================================================================
# GAME STATE
# ============================================================================

class GameState:
    def __init__(self) -> None:
        self.player: Optional[dict[str, Any]] = None

        self.enemies: list[
            dict[str, Any]
        ] = []

        self.obstacles: list[
            dict[str, Any]
        ] = []

        self.bullets: list[
            dict[str, Any]
        ] = []

        self.coins: list[
            dict[str, Any]
        ] = []

        self.timestamp = time.monotonic()

    def update(
        self,
        data: Any,
    ) -> None:

        if not isinstance(data, dict):
            return

        player = data.get("player")

        if isinstance(
            player,
            dict,
        ):
            self.player = player

        for name in (
            "enemies",
            "obstacles",
            "bullets",
            "coins",
        ):
            value = data.get(name)

            if isinstance(
                value,
                list,
            ):
                setattr(
                    self,
                    name,
                    value,
                )

        self.timestamp = time.monotonic()

    def nearest_enemy(
        self,
    ) -> Optional[
        tuple[dict[str, Any], float]
    ]:

        if not self.player:
            return None

        player_xy = _extract_xy(
            self.player
        )

        if not player_xy:
            return None

        px, py = player_xy

        nearest = None
        nearest_distance = None

        for enemy in self.enemies:

            enemy_xy = _extract_xy(
                enemy
            )

            if not enemy_xy:
                continue

            ex, ey = enemy_xy

            distance = _distance(
                px,
                py,
                ex,
                ey,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest = enemy
                nearest_distance = distance

        if (
            nearest is None
            or nearest_distance is None
        ):
            return None

        return (
            nearest,
            nearest_distance,
        )

    def nearest_obstacle(
        self,
    ) -> Optional[
        tuple[dict[str, Any], float]
    ]:

        if not self.player:
            return None

        player_xy = _extract_xy(
            self.player
        )

        if not player_xy:
            return None

        px, py = player_xy

        nearest = None
        nearest_distance = None

        for obstacle in self.obstacles:

            obstacle_xy = _extract_xy(
                obstacle
            )

            if not obstacle_xy:
                continue

            ox, oy = obstacle_xy

            distance = _distance(
                px,
                py,
                ox,
                oy,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest = obstacle
                nearest_distance = distance

        if (
            nearest is None
            or nearest_distance is None
        ):
            return None

        return (
            nearest,
            nearest_distance,
        )


# ============================================================================
# NEXT PART
# ============================================================================
# ============================================================================
# GAME STATE INSPECTION
# ============================================================================

async def _inspect_game(
    page: Page,
) -> GameState:
    """
    O'yinning ichki holatini tekshiradi.

    Avval JavaScript global obyektlarini,
    keyin DOM elementlarini tekshiradi.
    """

    state = GameState()

    try:
        data = await page.evaluate(
            GAME_INSPECTOR_JS
        )

        state.update(data)

    except Exception as exc:
        logger.debug(
            "[GAME VIDEO] "
            "Game inspection failed: %s",
            exc,
        )

    return state


# ============================================================================
# START GAME
# ============================================================================

async def _find_start_button(
    page: Page,
):
    """
    Start/Boshlash tugmasini topadi.
    """

    selectors = [
        # English
        "button:has-text('Start')",
        "button:has-text('START')",
        "button:has-text('Start Game')",
        "button:has-text('Play')",
        "button:has-text('PLAY')",

        # Uzbek
        "button:has-text('Boshlash')",
        "button:has-text('BOSHLASH')",
        "button:has-text('Boshlash!')",
        "button:has-text('O‘ynash')",
        "button:has-text(\"O'ynash\")",
        "button:has-text('OYNASH')",

        # IDs
        "#start",
        "#startButton",
        "#start-btn",
        "#startGame",
        "#start-game",
        "#play",
        "#playButton",
        "#play-btn",
        "#playGame",

        # Classes
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
            locator = (
                page
                .locator(selector)
                .first
            )

            if await locator.count() == 0:
                continue

            if not await locator.is_visible(
                timeout=200
            ):
                continue

            return locator

        except Exception:
            continue

    # Text fallback.
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
            locator = (
                page
                .locator(selector)
                .first
            )

            if await locator.count() == 0:
                continue

            if not await locator.is_visible(
                timeout=150
            ):
                continue

            return locator

        except Exception:
            continue

    return None


async def _start_game(
    page: Page,
) -> bool:
    """
    Start tugmasini bosadi.

    True:
        Start topildi va bosildi.

    False:
        Start topilmadi.
    """

    target = await _find_start_button(
        page
    )

    if target is None:

        logger.info(
            "[GAME VIDEO] "
            "Start button not found."
        )

        return False

    try:

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
            "[GAME VIDEO] "
            "Start button clicked."
        )

        # O'yinning JS loop'i ishga tushishi
        # uchun qisqa vaqt.
        await page.wait_for_timeout(
            350
        )

        return True

    except Exception as exc:

        logger.warning(
            "[GAME VIDEO] "
            "Could not click Start: %s",
            exc,
        )

        return False


# ============================================================================
# GAME RUNNING DETECTION
# ============================================================================

async def _wait_until_game_started(
    page: Page,
    timeout_ms: int = 3000,
) -> bool:
    """
    O'yin haqiqatan ishga tushganini aniqlashga urinadi.

    Bu Start bosilgandan keyin recordingni
    darhol emas, o'yin loop'i ishga tushgach
    boshlash uchun ishlatiladi.
    """

    deadline = (
        time.monotonic()
        + timeout_ms / 1000
    )

    while (
        time.monotonic()
        < deadline
    ):

        try:

            state = await _inspect_game(
                page
            )

            if state.player:
                return True

            # Canvas/DOM o'yinlar uchun
            # activity tekshiriladi.
            active = await page.evaluate(
                """
                () => {
                    const canvas =
                        document.querySelector("canvas");

                    if (canvas) {
                        const rect =
                            canvas.getBoundingClientRect();

                        return (
                            rect.width > 0 &&
                            rect.height > 0
                        );
                    }

                    return true;
                }
                """
            )

            if active:
                # Universal fallback:
                # Start bosilgandan keyin ozgina
                # vaqt o'tishi o'yin boshlangan
                # deb olinadi.
                return True

        except Exception:
            pass

        await page.wait_for_timeout(
            120
        )

    return False


# ============================================================================
# INPUT HELPERS
# ============================================================================

async def _press_key(
    page: Page,
    key: str,
    hold_ms: int = KEY_HOLD_MS,
) -> None:
    """
    Tugmani xavfsiz bosadi.
    """

    try:
        await page.keyboard.down(
            key
        )

        await page.wait_for_timeout(
            hold_ms
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


async def _press_once(
    page: Page,
    key: str,
) -> None:
    try:
        await page.keyboard.press(
            key
        )
    except Exception:
        pass


async def _fire(
    page: Page,
) -> None:
    """
    Turli o'yinlarda ishlatiladigan
    umumiy o'q otish tugmalarini sinaydi.
    """

    fire_keys = [
        "Space",
        "KeyX",
        "KeyZ",
        "Control",
    ]

    # Bir siklda hammasini bosish o'yinni
    # haddan tashqari tezlatib yubormasligi
    # uchun bittasini tanlaymiz.
    for key in fire_keys:

        try:
            await page.keyboard.press(
                key
            )

            logger.debug(
                "[GAME VIDEO] "
                "Fire key: %s",
                key,
            )

            return

        except Exception:
            continue


# ============================================================================
# MOVEMENT
# ============================================================================

async def _move_right(
    page: Page,
    duration_ms: int = KEY_HOLD_MS,
) -> None:

    await _press_key(
        page,
        "ArrowRight",
        duration_ms,
    )


async def _move_left(
    page: Page,
    duration_ms: int = KEY_HOLD_MS,
) -> None:

    await _press_key(
        page,
        "ArrowLeft",
        duration_ms,
    )


async def _jump(
    page: Page,
) -> None:

    # Bir nechta keng tarqalgan sakrash
    # tugmalaridan bittasini ishlatamiz.
    await _press_once(
        page,
        "Space",
    )


# ============================================================================
# GAME AREA
# ============================================================================

async def _get_game_area(
    page: Page,
):
    """
    O'yin maydonini topadi.
    """

    selectors = [
        "canvas",
        "#gameCanvas",
        "#game",
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

            if box:
                return target, box

        except Exception:
            continue

    return None, None


async def _active_game_click(
    page: Page,
) -> None:
    """
    Canvas/touch asosidagi o'yinlar uchun
    faol click/tap qiladi.
    """

    target, box = (
        await _get_game_area(page)
    )

    if target is None or box is None:
        return

    points = [
        (0.50, 0.50),
        (0.35, 0.50),
        (0.65, 0.50),
        (0.50, 0.35),
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


# ============================================================================
# AI DECISION
# ============================================================================

class AIDecision:
    """
    AI tomonidan tanlangan harakat.
    """

    def __init__(
        self,
        action: str,
        reason: str,
    ) -> None:

        self.action = action
        self.reason = reason


def _decide_action(
    state: GameState,
) -> AIDecision:

    # ------------------------------------------------------------
    # Player topilmasa:
    # Universal harakat.
    # ------------------------------------------------------------

    if not state.player:

        return AIDecision(
            "explore",
            "player_not_detected",
        )

    # ------------------------------------------------------------
    # Obstacle tekshirish.
    # ------------------------------------------------------------

    obstacle_info = (
        state.nearest_obstacle()
    )

    if obstacle_info:

        _, obstacle_distance = (
            obstacle_info
        )

        if obstacle_distance < 90:

            return AIDecision(
                "jump",
                "obstacle_near",
            )

    # ------------------------------------------------------------
    # Enemy tekshirish.
    # ------------------------------------------------------------

    enemy_info = (
        state.nearest_enemy()
    )

    if enemy_info:

        enemy, enemy_distance = (
            enemy_info
        )

        player_xy = _extract_xy(
            state.player
        )

        enemy_xy = _extract_xy(
            enemy
        )

        if (
            player_xy
            and enemy_xy
        ):

            px, py = player_xy
            ex, ey = enemy_xy

            # ----------------------------------------------------
            # Juda yaqin dushman → QOCHISH
            # ----------------------------------------------------

            if (
                enemy_distance
                <= ENEMY_DANGER_DISTANCE
            ):

                if ex >= px:

                    return AIDecision(
                        "escape_left",
                        "enemy_too_close",
                    )

                return AIDecision(
                    "escape_right",
                    "enemy_too_close",
                )

            # ----------------------------------------------------
            # Hujum masofasi → O'TISH
            # ----------------------------------------------------

            if (
                enemy_distance
                <= ENEMY_ATTACK_DISTANCE
            ):

                return AIDecision(
                    "attack",
                    "enemy_in_attack_range",
                )

            # ----------------------------------------------------
            # Dushman uzoqda → unga yaqinlashish
            # ----------------------------------------------------

            if (
                enemy_distance
                <= ENEMY_FAR_DISTANCE
            ):

                if ex > px:

                    return AIDecision(
                        "move_right",
                        "approaching_enemy",
                    )

                return AIDecision(
                    "move_left",
                    "approaching_enemy",
                )

    # ------------------------------------------------------------
    # Default faol harakat.
    # ------------------------------------------------------------

    return AIDecision(
        "explore",
        "no_immediate_threat",
    )


# ============================================================================
# NEXT PART
# ============================================================================
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


# ─────────────────────────────────────────────────────────────────────────────
# END
# ─────────────────────────────────────────────────────────────────────────────