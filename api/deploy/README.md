# Patcher API deployment

Operational notes for the live Patcher API service on Linode. The systemd
units in this directory drive the catalog-refresh cadence; this README
covers the bits that aren't expressed in those units.

## Architecture

The Patcher API runs as a long-lived `patcher-api.service` (uvicorn +
FastAPI). Catalog refresh happens **in place** via a systemd timer:

- `patcher-catalog-refresh.timer` fires daily at 04:00 UTC.
- It triggers `patcher-catalog-refresh.service`, which runs
  `ingest.py all` as the `patcher` user. The ingest module upserts rows
  into the live SQLite DB, so reads stay consistent throughout.
- After the ingest completes, the refresh service restarts
  `patcher-api.service` so the FastAPI app picks up the new
  `app.state.catalog_sha` for `/apps*` ETag responses. Restart takes <1
  second.

No GitHub Actions workflow, no upload endpoint, no deploy tokens. Earlier
iterations had all three; they were over-engineered for a single-tenant
deploy and the `deploy_tokens` table getting wiped by the wholesale-DB-swap
flow caused recurring 401 outages on the catalog refresh path.

## Environment file

Both `patcher-api.service` and `patcher-catalog-refresh.service` read
configuration from environment variables prefixed with `PATCHER_API_`,
loaded from `/etc/patcher-api/env` via systemd's `EnvironmentFile=`. The
most important variable:

```
PATCHER_API_DATABASE_URL="sqlite+aiosqlite:////var/lib/patcher-api/patcher_api.db"
```

Note the four slashes after `sqlite+aiosqlite:` — three for the URL scheme
separator plus the leading slash of the absolute path.

The `Settings` class in `patcher_api.config` also auto-loads from this
path via pydantic-settings, so any maintenance script run as a user that
can read the file (typically the `patcher` user) picks up the same
configuration without sourcing anything explicitly.

## One-time setup

```bash
# Install the systemd units
sudo cp /opt/patcher/api/deploy/patcher-catalog-refresh.service \
        /etc/systemd/system/
sudo cp /opt/patcher/api/deploy/patcher-catalog-refresh.timer \
        /etc/systemd/system/

# Pick up the new units
sudo systemctl daemon-reload

# Enable + start the timer (Persistent=true so it catches up after reboots)
sudo systemctl enable --now patcher-catalog-refresh.timer
```

To migrate off the old swap setup, remove the obsolete units before the
new ones land:

```bash
sudo systemctl disable --now patcher-catalog-swap.path
sudo rm /etc/systemd/system/patcher-catalog-swap.{service,path}
sudo rm -rf /var/lib/patcher-api/incoming  # no longer used
```

The `/var/lib/patcher-api/backups/` directory and its existing contents
can stay as a historical record or be cleaned up; the new flow doesn't
add new files there.

## Manual refresh

To trigger an out-of-band refresh:

```bash
sudo systemctl start patcher-catalog-refresh.service
```

This is synchronous from systemd's point of view — the command returns
when the ingest + restart cycle completes. To watch progress:

```bash
sudo journalctl -u patcher-catalog-refresh.service -f
```

## Observability

```bash
# When will the next refresh fire?
sudo systemctl list-timers patcher-catalog-refresh.timer

# Did the most recent refresh succeed?
sudo systemctl status patcher-catalog-refresh.service

# Full log of the most recent refresh
sudo journalctl -u patcher-catalog-refresh.service -n 200 --no-pager

# Live tail during a manual run
sudo journalctl -u patcher-catalog-refresh.service -f
```

A failed refresh leaves `patcher-catalog-refresh.service` in
`failed` state. The journal has the full stderr from `ingest.py` and the
exit status of the `runuser` invocation. Common failure modes:

- **Upstream rate-limit or transient network failure**: ingest exits
  non-zero with an httpx exception in the journal. Re-run manually after
  the upstream recovers; the next scheduled run will also retry.
- **`patcher` user can't read `/etc/patcher-api/env`**: pydantic-settings
  silently falls back to relative defaults and the ingest writes to the
  wrong DB. Verify mode/ownership on the env file (`root:patcher 0640`
  is the documented convention).
- **Disk space**: the upserts are row-by-row; running out of space
  mid-ingest leaves the DB partially updated. SQLite's `journal_mode=WAL`
  + `synchronous=NORMAL` means the WAL is replayable on next read, so
  the DB shouldn't corrupt — but the catalog will reflect a partial
  state until the next successful refresh.

## Patcher service operations

Standard systemd commands for the API itself:

```bash
sudo systemctl status patcher-api.service
sudo systemctl restart patcher-api.service
sudo journalctl -u patcher-api.service -f
```

The refresh service handles the restart automatically after each ingest.
Manual restarts are only needed when deploying code changes to the API
itself (e.g., a `git pull` on `/opt/patcher` followed by a service
restart to pick up the new code).
