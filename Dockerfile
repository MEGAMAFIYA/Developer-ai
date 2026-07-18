## ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

# gcc is required to compile asyncpg's C extension on platforms without wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY gamehub/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


## ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="Kichik Oyinlar Bot"
LABEL org.opencontainers.image.description="Telegram mini-games bot + FastAPI WebApp"

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source
COPY gamehub/ gamehub/

# Pre-create logs directory so RotatingFileHandler never fails on startup
RUN mkdir -p gamehub/logs

# Run as non-root for security
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Render injects PORT at runtime (typically 10000).
# The app falls back to 8000 when PORT is unset (Replit / local dev).
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check — Render also polls /health; this gives Docker itself visibility
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health', timeout=4)"

CMD ["sh", "-c", "cd gamehub && python main.py"]
