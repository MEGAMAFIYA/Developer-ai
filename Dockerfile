## ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY gamehub/requirements.txt .

RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    -r requirements.txt

# Playwright Python package
RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    playwright

# Playwright FFmpeg binary.
# Required by Playwright when record_video_dir is used.
ENV PLAYWRIGHT_BROWSERS_PATH=/playwright

RUN PLAYWRIGHT_BROWSERS_PATH=/playwright \
    playwright install ffmpeg


## ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Kichik Oyinlar Bot"
LABEL org.opencontainers.image.description="Telegram mini-games bot + FastAPI WebApp"

# Chromium:
# HTML Mini App / game ni ishga tushirish uchun.
#
# System FFmpeg:
# Qo'shimcha video conversion uchun.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        ffmpeg \
        ca-certificates \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Python packages
COPY --from=builder /install /usr/local

# Playwright FFmpeg binary
COPY --from=builder /playwright /playwright

WORKDIR /app

# Application source
COPY gamehub/ gamehub/

# Required directories
RUN mkdir -p \
        gamehub/logs \
        gamehub/webapp/games \
        gamehub/webapp/assets/games \
        gamehub/webapp/generated_videos

# Non-root user
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app /playwright

USER appuser

# Render injects PORT at runtime
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/playwright

# Health check
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health', timeout=4)"

# Start bot + FastAPI
CMD ["sh", "-c", "cd gamehub && python main.py"]