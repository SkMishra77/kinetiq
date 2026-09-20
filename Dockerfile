# Kinetiq — multi-stage image using uv.
# Non-root, read-only rootfs, healthcheck in pure Python.

# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY README.md ./README.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime ---------------------------------------------------------------
FROM python:3.12-slim-trixie AS runtime
RUN groupadd -r -g 10001 kinetiq \
 && useradd -r -u 10001 -g kinetiq -d /app -s /usr/sbin/nologin kinetiq \
 && mkdir -p /data && chown -R kinetiq:kinetiq /data
WORKDIR /app
COPY --from=builder --chown=kinetiq:kinetiq /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8765 \
    KINETIQ_HOST=0.0.0.0 \
    KINETIQ_DATA_DIR=/data \
    FASTMCP_MASK_ERROR_DETAILS=true \
    FASTMCP_STATELESS_HTTP=true \
    FASTMCP_SHOW_SERVER_BANNER=false
USER kinetiq
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request; r=urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8765\")}/health', timeout=3); sys.exit(0 if r.status==200 else 1)"]
CMD ["kinetiq", "serve"]
