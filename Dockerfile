# Patcher API container image. AI-assisted initial draft; the maintainer isn't a
# Docker expert, so community PRs (correctness, size, security, build perf) are welcome.

# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.9.7

FROM python:${PYTHON_VERSION}-slim AS builder

# Re-declared here so ${UV_VERSION} is visible to the COPY below (global ARGs aren't).
ARG UV_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/patcher/.venv

# uv from its official image, pinned by tag (not digest) for a community example.
COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /uvx /usr/local/bin/

WORKDIR /opt/patcher

# Metadata only first, so dependency resolution caches across source-only changes.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY api/pyproject.toml ./api/pyproject.toml

# Only __about__.py so hatchling can read __version__ at resolve time; full source follows.
COPY src/patcher/__about__.py ./src/patcher/__about__.py

# Resolve deps; --frozen keeps uv.lock read-only during the build.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package patcher-api --no-install-project

# Bring in the full source and install the workspace projects on the resolved env.
COPY src/ ./src/
COPY api/ ./api/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package patcher-api


FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/patcher/.venv/bin:${PATH}" \
    PATCHER_API_DATABASE_URL="sqlite+aiosqlite:////data/patcher_api.db" \
    PATCHER_API_ENV_FILE="/etc/patcher-api/env"

# curl for HEALTHCHECK, tini for init/signal handling without --init.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user with a fixed UID/GID for predictable /data ownership on bind mounts.
RUN groupadd --system --gid 1000 patcher \
    && useradd --system --uid 1000 --gid patcher --home-dir /opt/patcher --shell /usr/sbin/nologin patcher \
    && mkdir -p /data /etc/patcher-api \
    && chown -R patcher:patcher /data /etc/patcher-api

WORKDIR /opt/patcher

COPY --from=builder --chown=patcher:patcher /opt/patcher /opt/patcher

USER patcher

EXPOSE 8000

# /health is a cheap no-DB-touch route; safe to poll frequently.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "patcher_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
