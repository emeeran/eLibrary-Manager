# Multi-stage Dockerfile for Dawnstar eBook Manager
# Stage 1: Builder
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies without dev packages
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY backend/app/ backend/app/
COPY frontend/ frontend/

# Create data directories and non-root user
RUN mkdir -p /app/library /app/dawnstar_data /app/static_covers /app/static_book_images && \
    adduser --disabled-password --gecos "" --uid 1000 dawnstar && \
    chown -R dawnstar:dawnstar /app

USER dawnstar

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
