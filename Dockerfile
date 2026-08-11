## ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY gamehub/requirements.txt .

# Application packages
RUN pip install \
    --no-cache-dir \
    -r requirements.txt

# Playwright
RUN pip install \
    --no-cache-dir \
    playwright

# Playwright FFmpeg binary
ENV PLAYWRIGHT_BROWSERS_PATH=/playwright

RUN mkdir -p /playwright \
    && playwright install ffmpeg


## ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Kichik Oyinlar Bot"
LABEL org.opencontainers.image.description="Telegram mini-games bot + FastAPI WebApp"


# ── System packages ───────────────────────────────────────────────────────────

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        ffmpeg \
        ca-certificates \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*


# ── Python packages ───────────────────────────────────────────────────────────

COPY --from=builder /usr/local /usr/local


# ── Playwright FFmpeg ─────────────────────────────────────────────────────────

COPY --from=builder /playwright /playwright


WORKDIR /app


# ── Application source ────────────────────────────────────────────────────────

COPY gamehub/ gamehub/


# ── Required directories ─────────────────────────────────────────────────────

RUN mkdir -p \
        gamehub/logs \
        gamehub/webapp/games \
        gamehub/webapp/assets/games \
        gamehub/webapp/generated_videos


# ── Non-root user ─────────────────────────────────────────────────────────────

RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /playwright


USER appuser


# ── Environment ──────────────────────────────────────────────────────────────

ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/playwright


# ── Health check ─────────────────────────────────────────────────────────────

HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health', timeout=4)"


# ── Start bot + FastAPI ───────────────────────────────────────────────────────

CMD ["sh", "-c", "cd gamehub && python main.py"]