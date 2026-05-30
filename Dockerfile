# Patcher API container image.
# This Dockerfile was AI-assisted in its initial draft. The Patcher maintainer
# is not a Docker expert; community contributions that improve correctness,
# image size, security, or build performance are welcome on GitHub.

# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/patcher/.venv

# Install uv from the official distroless image. Pinning by tag rather than
# digest is intentional for a community-facing example; bump as needed.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /opt/patcher

# Copy only the metadata files first so dependency resolution caches across
# source-only changes. The api/ workspace member needs its own pyproject.toml
# present at resolve time because the root pyproject declares it as a member.
COPY pyproject.toml uv.lock README.md ./
COPY api/pyproject.toml ./api/pyproject.toml

# Materialize the patcherctl source tree just enough for hatchling to read
# __version__ during workspace resolution. The full source is copied next.
COPY src/patcher/__about__.py ./src/patcher/__about__.py

# Resolve the lockfile, building the API workspace member and its deps.
# --frozen refuses to update uv.lock; that's what we want in a build context.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package patcher-api --no-install-project

# Now bring in the rest of the source and install the workspace projects
# themselves on top of the resolved env.
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

# curl is used by HEALTHCHECK. tini gives us a proper init for signal handling
# under `docker run` without --init.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user. UID/GID are fixed so bind-mounted /data volumes have
# predictable ownership on the host side.
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
