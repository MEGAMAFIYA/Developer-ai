## ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY gamehub/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Playwright Python package
RUN pip install --no-cache-dir --prefix=/install playwright


## ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Kichik Oyinlar Bot"
LABEL org.opencontainers.image.description="Telegram mini-games bot + FastAPI WebApp"

# Chromium — HTML Mini App'ni ishga tushirish
# FFmpeg — yozilgan videoni MP4 qilish
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        ffmpeg \
        ca-certificates \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Python packages
COPY --from=builder /install /usr/local

WORKDIR /app

# Application source
COPY gamehub/ gamehub/

# Required directories
RUN mkdir -p \
        gamehub/logs \
        gamehub/webapp/games \
        gamehub/webapp/assets/games

# Non-root user
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app

USER appuser

# Render injects PORT at runtime
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=0

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health', timeout=4)"

# Start bot + FastAPI
CMD ["sh", "-c", "cd gamehub && python main.py"]