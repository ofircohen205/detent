# syntax=docker/dockerfile:1

# ─── Stage 1: Builder ────────────────────────────────────────────────────────
#
# Uses uv inside the build stage to install dependencies into a virtual
# environment, then copies only the venv + package into the slim runtime image.
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy lockfiles first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies into an isolated venv
RUN uv sync --no-dev --frozen

# Copy the rest of the source
COPY . .


# ─── Stage 2: Runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd -r detent && useradd -r -g detent detent

WORKDIR /app

# Copy the virtual environment built in the builder stage
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY --from=builder /build/detent /app/detent
COPY --from=builder /build/pyproject.toml /app/pyproject.toml

# Optional: default config (can be overridden via volume mount)
COPY --from=builder /build/detent.yaml /app/detent.yaml

# Make the venv's Python the default interpreter
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DETENT_CONFIG=/app/detent.yaml \
    DETENT_LOG_LEVEL=INFO

# Port for the HTTP reverse proxy
EXPOSE 7070

USER detent

# Health check: hit the proxy liveness endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7070/healthz')" || exit 1

# Default command: start the proxy
CMD ["python", "-m", "detent.proxy.http_proxy"]
