---
description: "Self-host the Patcher API: build the Docker image, run it locally or in your fleet, populate the catalog via the ingest pipeline, and configure environment variables."
---

(self-hosting)=

# Self-Hosting

:::{rst-class} lead
Run your own copy of the Patcher catalog service. Community-supported.
:::

---

The Patcher API is a FastAPI service that stitches macOS app patching metadata from Installomator, Homebrew Cask, AutoPkg, and Jamf App Installers into a single queryable catalog. The public deployment at <https://api.patcherctl.dev> is the easiest path. This page is for the cases where that isn't a fit.

## Who This Is For

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:server-16` MacAdmins running their own mirror
Keep catalog reads inside your network for latency, audit, or policy reasons.
:::

:::{grid-item-card} {iconify}`octicon:shield-lock-16` Air-gapped or restricted fleets
The container only needs network access when the ingest job runs. The serving side is offline-friendly.
:::

:::{grid-item-card} {iconify}`octicon:beaker-16` Contributors and tinkerers
Iterate on ingest sources, stitch rules, or the MCP server without touching production.
:::

:::{grid-item-card} {iconify}`octicon:plug-16` Customized catalogs
Fork the ingest pipeline to add internal sources, suppress upstreams, or change the refresh schedule.
:::
::::

## Honest Framing

```{important}
The Dockerfile and the compose snippet on this page were drafted with AI assistance. The Patcher maintainer is not a Docker expert and does not run Patcher in containers in production (the public deployment uses systemd on a Linode VM). Treat this setup as community-supported. Improvements to the image, security posture, build performance, or compose layout are very welcome via pull request.
```

For the conceptual model of how the service is structured (FastAPI app, ingest pipeline, stitch layer, MCP sub-app), read {doc}`architecture/index` first. This page covers operations, not internals.

## Build the Image

The Dockerfile lives at the repo root. It uses [uv](https://docs.astral.sh/uv/) inside a multi-stage build, materializes the `patcher-api` workspace member, and ships a non-root runtime user with a `/health` healthcheck baked in.

```bash
$ git clone https://github.com/liquidz00/Patcher.git
$ cd Patcher
$ docker build --tag patcher-api:local .
```

The default Python is 3.13. Override with `--build-arg PYTHON_VERSION=3.12` if you need a different interpreter.

## Run It

The image exposes port 8000 and stores the catalog at `/data/patcher_api.db` by default. Mount a volume there so the database survives container restarts.

```bash
$ docker run --rm \
    --name patcher-api \
    --publish 8000:8000 \
    --volume patcher-catalog:/data \
    --env PATCHER_API_ADMIN_TOKEN="change-me" \
    patcher-api:local
```

Visit <http://localhost:8000/health> to confirm the service is up.

:::{admonition} Important
:class: caution

Building and running the image does **not** populate the catalog. On first boot the container drops in a small `SEED_ON_STARTUP` sample (a handful of apps) so `/apps` isn't empty, but the real catalog of thousands of apps comes **only** from the separate {ref}`ingest step <self-hosting-ingest>` below. Don't expect a full catalog straight from `docker run`.
:::

:::{note}
The container runs `alembic upgrade head` on startup, so it builds the database schema on first boot and applies later migrations automatically. You don't manage the schema yourself.

**Upgrading from a pre-Alembic image:** if you previously ran an image that created its schema implicitly, adopt the existing database once before starting the new image, or the first migration will try to recreate tables that already exist:

```bash
$ docker run --rm \
    --volume patcher-catalog:/data \
    --workdir /opt/patcher/api \
    --entrypoint alembic \
    patcher-api:local stamp head
```
:::

### Environment Variables

All runtime configuration uses the `PATCHER_API_` prefix. The full list lives in `api/patcher_api/config.py`; the variables that matter most for self-hosting:

| Variable | Purpose | Default |
|---|---|---|
| `PATCHER_API_DATABASE_URL` | SQLAlchemy URL for the catalog DB. The image defaults to a SQLite file at `/data/patcher_api.db`. | `sqlite+aiosqlite:////data/patcher_api.db` |
| `PATCHER_API_ADMIN_TOKEN` | Shared secret gating `/admin/*` write endpoints. Unset means fail-closed (every write rejected). | unset |
| `PATCHER_API_MCP_ALLOWED_ORIGINS` | JSON list of browser origins permitted to call `/mcp`. Native MCP clients (Claude Desktop, Cursor) pass without an Origin header and bypass the check. | `["https://claude.ai"]` |
| `PATCHER_API_GITHUB_TOKEN` | Authenticates ingest-time calls to `api.github.com` (5000/hr instead of the 60/hr shared budget). Strongly recommended on a busy ingest schedule. | unset |
| `PATCHER_API_SEED_ON_STARTUP` | Idempotent smoke-seed of a few catalog rows on first boot. Safe to leave on. | `true` |
| `PATCHER_API_ENV_FILE` | Path inside the container to read env vars from. Lets you mount a secrets file instead of passing `--env`. | `/etc/patcher-api/env` |

(self-hosting-ingest)=

## Populate the Catalog

The serving image starts with an empty (or smoke-seeded) catalog. Real data comes from the ingest pipeline at `api/scripts/ingest.py`, which pulls each upstream source, writes per-source rows, and runs the stitch pass that joins them into canonical `apps` records.

A one-shot ingest against the same volume the API uses:

```bash
$ docker run --rm \
    --volume patcher-catalog:/data \
    --env PATCHER_API_DATABASE_URL="sqlite+aiosqlite:////data/patcher_api.db" \
    --env PATCHER_API_GITHUB_TOKEN="ghp_..." \
    --workdir /opt/patcher/api \
    --entrypoint python \
    patcher-api:local scripts/ingest.py all
```

`all` runs every source (Installomator, Homebrew Cask, AutoPkg, Jamf App Installers) and then the stitch phase. Each source can be run individually (`installomator`, `homebrew`, `autopkg`, `jai`, `stitch`); see the script's `--help` for flags including `--force` (bypass SHA gating) and `--resolve` (evaluate Installomator's dynamic `downloadURL` / `appNewVersion` expressions during ingest, slower but more complete).

```{note}
A full ingest currently takes 10 to 15 minutes against fresh upstreams. The public deployment runs it once a day on a systemd timer (`api/deploy/patcher-catalog-refresh.timer`). Schedule yours via cron, a Kubernetes `CronJob`, a host-side `systemd.timer`, or whatever your orchestrator prefers.
```

```{warning}
The API process caches the catalog SHA at startup and uses it as the ETag for `/apps*` responses. After a fresh ingest the running container will not pick up the new hash until it restarts. The reference compose file does not automate this; on the production VM a systemd `ExecStartPost=` restarts the API after the timer fires. On Docker you can either run the API with `--restart always` and trigger a manual restart after the ingest job, or wrap the ingest in a script that runs `docker compose restart api` on completion.
```

## Compose Example

A reference `docker-compose.yml` lives at the repo root. It defines two services backed by a shared named volume:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    image: patcher-api:local
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      PATCHER_API_DATABASE_URL: "sqlite+aiosqlite:////data/patcher_api.db"
    volumes:
      - catalog:/data
    healthcheck:
      test: ["CMD", "curl", "--fail", "--silent", "http://127.0.0.1:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

  ingest:
    image: patcher-api:local
    build:
      context: .
      dockerfile: Dockerfile
    profiles: ["ingest"]
    environment:
      PATCHER_API_DATABASE_URL: "sqlite+aiosqlite:////data/patcher_api.db"
      # PATCHER_API_GITHUB_TOKEN: "ghp_..."
    volumes:
      - catalog:/data
    working_dir: /opt/patcher/api
    entrypoint: ["/usr/bin/tini", "--"]
    command: ["python", "scripts/ingest.py", "all"]

volumes:
  catalog:
```

The `ingest` service uses the `ingest` profile so `docker compose up` only starts the API. Trigger an ingest on demand with:

```bash
$ docker compose --profile ingest run --rm ingest
```

Wire that command into your host's cron or scheduler.

## Caveats

A few things to know before this goes anywhere serious.

::::{markers}
:icon: octicon:alert-16

:::{marker} SQLite under multiple workers
The default `uvicorn` command runs a single worker. SQLite locking gets unhappy under a multi-worker `uvicorn` against the same file. If you need more concurrency, put a reverse proxy in front of multiple containers each with their own DB, or migrate the storage to Postgres (the SQLAlchemy models are Postgres-friendly, but this path is not regularly tested).
:::

:::{marker} The `seed_on_startup` smoke data
First boot drops a small set of known apps into the catalog so `/apps` returns something before your first ingest finishes. Set `PATCHER_API_SEED_ON_STARTUP=false` if that's not desired.
:::

:::{marker} The MCP sub-app at `/mcp`
Hosted alongside the REST routes on the same port. If you don't need it, point browser MCP clients elsewhere via `PATCHER_API_MCP_ALLOWED_ORIGINS`. The sub-app itself can't be unmounted without a code change.
:::

:::{marker} Image size and security
The reference image is a community starting point, not a hardened production base. There's no distroless runtime, no SBOM step, no image-signing flow. If you ship this in a regulated environment, treat the Dockerfile as a draft to harden.
:::
::::

## Related Reading

- {doc}`architecture/index` for how the service is laid out and the pipelines that produce the catalog.
- {doc}`/reference/api/endpoints` for the REST surface the running container exposes.
- {doc}`/guides/agents` if you also want to expose the MCP endpoint to AI clients.

## Contributing

If you run Patcher in a container and have hard-won fixes (smaller image, better caching, multi-arch builds, a real Helm chart, a Kubernetes manifest), open a PR. The Dockerfile and this page are explicitly community-improvable; see {doc}`contributing` for the workflow.
