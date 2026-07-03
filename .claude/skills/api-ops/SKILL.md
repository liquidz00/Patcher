---
name: api-ops
description: |
  Operate and troubleshoot the Patcher API service (`api/patcher_api/`) on its
  Linux host. Two modes:

  1. STATUS SWEEP (`/api-ops`, `/api-status`, "check the api", "is the api
     healthy", "run a health check") — a read-only pass over the systemd units,
     cloudflared tunnel, app endpoints, database, disk, and the Healthchecks.io
     monitors, reporting green/yellow/red per component.
  2. TROUBLESHOOTING (a symptom like "502 through cloudflared" / "service won't
     start", or pasted logs) — walks the known failure modes (KEYRING_BACKEND,
     cloudflared outbound-only, SQLite locking, systemd perms, deploy-token
     gating, restart loops, ingest failures).

  Also helps translate the systemd gotchas to a user's own Docker setup on a
  best-effort basis (Docker is not officially supported).

  Invoke on: "/api-ops", "/api-status", "patcher api won't start", "502 from
  cloudflared", "keyring error on linux", "is the api healthy", "why is
  patcher-deploy down", "schema-audit keeps flapping", or a pasted systemd /
  cloudflared / uvicorn log.
---

# api-ops

Patcher's API service (`api/patcher_api/`) is the only piece intended to run on
a Linux host. The documented deploy is **uvicorn under systemd, fronted by a
cloudflared tunnel**. No inbound ports beyond 22/80/443 are opened. SQLite +
SQLAlchemy 2.0 async is the backing store. `/apps*` and `/stats` are public;
`/admin/*` is gated by a deploy token.

This skill has two modes: a proactive **status sweep** and reactive
**troubleshooting**. A sweep that finds a problem flows straight into the
matching troubleshooting gotcha below.

**Everything here is read-only.** Report findings and recommend fixes; let the
user run anything that changes state (including Healthchecks.io dashboard edits).

## Host layout (the map)

| Thing | Path / name |
|---|---|
| Code checkout (owner: the deploy code user) | `/opt/patcher` |
| Virtualenv | `/opt/patcher/.venv` |
| SQLite DB (owner: `patcher`) | `/var/lib/patcher-api/patcher_api.db` |
| Service env file | `/etc/patcher-api/env` |
| Deploy sentinel (touched by `/admin/deploy`) | `/var/lib/patcher-api/deploy-requested` |
| API service | `patcher-api.service` (box-only, not in repo) |
| Tunnel | `cloudflared.service` |

The `patcher-api.service` unit lives only on the box. **Discover its port, user,
and ExecStart at runtime** (`systemctl cat patcher-api.service`) rather than
assuming, the app binds a localhost port that cloudflared fronts.

---

# Mode A: status sweep

Run these read-only checks in order and report a per-component verdict. Don't
stop at the first yellow, complete the sweep so the summary is whole.

### 1. Discover the running config

```bash
systemctl cat patcher-api.service | grep -iE 'ExecStart|User|Environment'
```

Note the **bind port** (feeds the endpoint checks) and the **service user**.

### 2. Core service health

```bash
systemctl is-active patcher-api.service cloudflared.service
systemctl show patcher-api.service -p NRestarts -p ActiveEnterTimestamp
journalctl -u patcher-api.service -p warning --since "6 hours ago" --no-pager
```

- `active` for both → green.
- A climbing `NRestarts` or a recent restart cluster → possible restart loop (see
  **G6**).
- Warnings/errors in the journal → pattern-match against the gotchas below.

### 3. Timers (scheduled jobs)

```bash
systemctl list-timers 'patcher-*' --no-pager
systemctl is-failed patcher-catalog-refresh.service patcher-schema-audit.service
```

Confirm `patcher-catalog-refresh.timer` and `patcher-schema-audit.timer` are
active with a sane `NEXT`. Then check each last run:

```bash
journalctl -u patcher-catalog-refresh.service -n 15 --no-pager
journalctl -u patcher-schema-audit.service -n 15 --no-pager
```

- Catalog refresh should end with a `Stitch summary: ... failed=0`.
- Schema audit should log `Schema audit clean: live database matches the models`.
  A non-zero exit means **schema drift**, investigate against the ORM models
  before the next deploy.

### 4. Deploy path unit

```bash
systemctl is-active patcher-deploy.path
journalctl -u patcher-deploy.service -n 20 --no-pager
```

The `.path` unit should be `active` (watching the sentinel). **A stale
"last deploy" here is NORMAL** — deploys are event-driven, see the monitoring
notes below. Only a `/fail` (non-zero deploy) is a real problem.

### 5. cloudflared tunnel

```bash
systemctl status cloudflared.service --no-pager | head -20
```

Tunnel should be connected. If the public URL 502s but the app answers on
localhost, that's **G2**, not a real outage.

### 6. App endpoints (use the discovered port; default 8000)

```bash
PORT=8000   # replace with the discovered bind port
curl -fsS "http://127.0.0.1:${PORT}/health"
curl -fsS "http://127.0.0.1:${PORT}/stats"
curl -fsS "http://127.0.0.1:${PORT}/apps" | head -c 200
```

- `/health` should return OK.
- `/stats` carries `last_refresh` (ingest freshness). **If `last_refresh` is older
  than ~26h, the daily catalog refresh has been missing** — the same threshold the
  external Lambda monitor alerts on. Cross-check step 3.
- `/apps` returning `[]` with no errors → **G7** (empty catalog / ingest never
  populated).

### 7. Database + disk

```bash
ls -l /var/lib/patcher-api/patcher_api.db
stat -c '%U:%G' /var/lib/patcher-api/patcher_api.db   # expect patcher:patcher
df -h /var/lib/patcher-api /opt/patcher
```

- DB owner mismatch → **G4** (write failures incoming).
- Low disk on the DB or code volume → flag; SQLite + backups + logs grow.

### 8. Healthchecks.io monitors (reference — read the dashboard)

These are external and their config lives **only in the dashboard** (not in the
repo). Report whether each matches the intended config in the monitoring table
below; a mismatch is itself a finding (it's how the schema-audit flap crept in).

### Status sweep output

```
Patcher API status — <date/time>

  patcher-api.service    ✅ active, 0 restarts in 6h
  cloudflared            ✅ connected
  catalog-refresh timer  ✅ last run clean, next 04:00 UTC
  schema-audit timer     ✅ audit clean, next 06:00 UTC
  deploy path            ✅ watching (last deploy 3d ago — normal, event-driven)
  /health                ✅ ok
  /stats last_refresh    ✅ 8h ago (< 26h)
  /apps                  ✅ non-empty
  database               ✅ patcher:patcher, not locked
  disk                   ✅ 62% used on /var/lib
  Healthchecks config    ⚠️  schema-audit schedule drift — see note

Overall: 🟡 one config drift, no service impact.
<then: the specifics + recommended fix for any yellow/red>
```

Green when everything's nominal. Yellow for config drift or soft signals with no
user impact. Red for an actual outage or failed job. Always end with the concrete
fix for anything not green.

---

# Monitoring topology & "don't panic" notes

The three Healthchecks.io dead-man's switches plus one external Lambda. **The
intended config below is the source of truth** — Healthchecks stores it only in
its dashboard, so drift between this table and the dashboard is a real finding.

| Check | Ping source | Intended config | Meaning |
|---|---|---|---|
| `patcher-catalog-refresh` | `patcher-catalog-refresh.service` (timer, 04:00 UTC) | Schedule `0 4 * * *`, grace 2h | Daily ingest+stitch ran and succeeded |
| `patcher-schema-audit` | `patcher-schema-audit.service` (timer, **06:00 UTC**) | Schedule `0 6 * * *`, grace 2h | Daily schema-drift audit ran clean |
| `patcher-deploy` | `patcher-deploy.service` (event-driven) | **Period 30d**, grace 20m | A deploy, *when one runs*, succeeded |

External: an **AWS Lambda** probes `/stats` and alerts if `last_refresh` > 26h —
independent liveness/freshness watch, separate from the box-side pings.

**Don't-panic note 1 — `patcher-deploy` is outcome-only, not cadence.** Deploys
fire only when CI (push to `main` under `api/**`) POSTs `/admin/deploy`, which
touches the sentinel and runs `patcher-deploy.service`. Deploys are therefore
*event-driven*; there is no cadence. The check's long period exists so that a
quiet stretch with no merges does **not** alarm. "Deploy DOWN: success signal did
not arrive on time" with a week+ since the last ping is a **false positive from a
mis-modeled period**, not a broken deploy. A real deploy problem shows up as a
`/fail` ping (immediate) or a `/start` with no finish inside grace (a hang). Only
those warrant action.

**Don't-panic note 2 — schema-audit schedule must track the 06:00 UTC timer.** If
the audit flaps DOWN then UP within seconds each day, the Healthchecks *schedule*
has drifted from the *timer's* actual run time. The timer runs at 06:00 UTC, so
the schedule must be `0 6 * * *`. A grace shorter than (schedule-to-actual-ping
gap) causes the momentary flap. This is a dashboard fix, not a code fix.

**Why config drift is invisible:** systemd unit timings live in version control
(`api/deploy/*.timer`); Healthchecks schedules/grace live only in the dashboard.
When a timer moves in git and the dashboard doesn't follow, nothing catches it.
Treat the table above as the reconciliation source.

---

# Mode B: troubleshooting

## Input shapes

Accept either:

1. **Symptom description** - "API returns 502 through cloudflared", "service
   won't start", "keyring import fails on boot", "admin endpoints return 401 with
   the right token".
2. **Pasted logs** - `journalctl -u patcher-api` output, `docker logs`, uvicorn
   stderr, cloudflared output.

If the user pastes logs without context, scan for the failure signature (table
below). If the user describes a symptom without logs, offer a likely diagnosis
first, then ask for the most relevant log source.

## Project-specific gotchas (the knowledge base)

These are the issues that *don't* surface from a generic FastAPI/Linux search.
Always check these before reaching for the obvious answers.

### G1. `KEYRING_BACKEND` is required on Linux

The patcherctl import chain pulls in the `keyring` library, which fails at import
time on Linux without a backend. The API service inherits this even though it
never touches the keychain.

**Signature in logs:**
```
keyring.errors.NoKeyringError: No recommended backend was available.
ModuleNotFoundError: No module named 'secretstorage'
```

**Fix:**
```bash
# In the systemd unit:
Environment=KEYRING_BACKEND=keyring.backends.null.Keyring

# Or in docker-compose:
environment:
  - KEYRING_BACKEND=keyring.backends.null.Keyring
```

This is documented in `CLAUDE.md:61` but easy to miss. Always check first when
the service fails on Linux import.

### G2. cloudflared is outbound-only

The tunnel pattern is `uvicorn (localhost) ← cloudflared (outbound to Cloudflare) ← public URL`.
The host doesn't open any inbound ports beyond 22/80/443. A 502 through the
tunnel usually means cloudflared can't reach uvicorn on the configured ingress
port, not that the public URL is wrong.

**Signature:**
- Public URL returns 502, but `curl http://localhost:<port>/health` from the host works.
- `cloudflared tunnel info <tunnel>` shows the tunnel as connected.

**Fix path:**
1. Confirm uvicorn's bind port (`systemctl cat patcher-api.service`) matches the
   cloudflared `ingress` config.
2. Confirm cloudflared is running on the same host (`systemctl status cloudflared`).
3. Check the `ingress` mapping in `~/.cloudflared/config.yml`.

### G3. SQLite locking under multi-worker uvicorn

SQLite handles concurrent reads fine but only one writer at a time. Running
uvicorn with `--workers 2+` against a single SQLite file produces intermittent
"database is locked" errors under load, especially during ingest.

**Signature:**
```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
```

**Fix:**
- For low-traffic deploys: run uvicorn with `--workers 1`. The async event loop
  handles concurrency within the single worker.
- For higher load: enable SQLite WAL mode in the DB init, but stay single-worker.
  Multi-worker is the wrong scaling axis for SQLite.

### G4. systemd `User=` permissions on the SQLite file

The service writes the DB as the `patcher` user; the DB file's owner must match.
If the service was bootstrapped as root and `User=` was added later, the db file
is unowned by the new user → service crashes on write.

**Signature:**
```
sqlite3.OperationalError: attempt to write a readonly database
PermissionError: [Errno 13] Permission denied: '/var/lib/patcher-api/patcher_api.db'
```

**Fix:**
```bash
chown -R patcher:patcher /var/lib/patcher-api/
chmod 0640 /var/lib/patcher-api/patcher_api.db
```

### G5. `/admin/*` 401 with the deploy token

Admin routes require a deploy token. Common causes of 401 with a
seemingly-correct token:

- Token has trailing whitespace from a copy-paste.
- Token was rotated but the client wasn't updated.
- Header is wrong; check the actual auth dep in `api/patcher_api/routes/admin.py`
  (`Authorization: Bearer <token>` vs a custom header).

**Fix path:**
1. Read the auth dependency in `api/patcher_api/` to confirm the header name.
2. `echo -n "<token>" | wc -c` and compare to the stored token length.
3. Confirm the server-side token env (`PATCHER_API_ADMIN_TOKEN`) is loaded
   (`systemctl show patcher-api -p Environment`, or check `/etc/patcher-api/env`).

### G6. uvicorn restart loop under systemd

Systemd's default `Restart=on-failure` + a config error → tight restart loop that
masks the real error in `journalctl`.

**Signature:**
```
patcher-api.service: Main process exited, code=exited, status=1/FAILURE
patcher-api.service: Failed with result 'exit-code'.
patcher-api.service: Scheduled restart job, restart counter is at N.
```

**Fix path:**
1. `systemctl stop patcher-api`
2. Run the ExecStart command by hand as the service user; the real error surfaces
   immediately without the systemd wrapper.
3. Fix and `systemctl start` again.

### G7. ingest pipeline failures / empty catalog

The ingest pipeline populates the canonical apps DB from Installomator labels,
Homebrew Cask, AutoPkg, and Jamf App Installers. First-boot or post-refresh
ingest can be slow (minutes) and may fail if outbound network is blocked.

**Signature:**
- API starts, but `/apps` returns an empty list.
- `/stats` `last_refresh` is null or very stale.

**Fix path:**
1. Check the catalog-refresh journal (`journalctl -u patcher-catalog-refresh.service`).
2. Confirm outbound HTTPS works from the host.
3. Trigger a manual refresh: run `scripts/ingest.py all` as the `patcher` user, or
   POST the admin deploy/refresh endpoint.

## Docker disclaimer

**Docker is not an officially supported deploy path.** There's no canonical
Dockerfile in the repo. If the user is debugging a Docker deploy, lead with this:

> Docker isn't officially supported for Patcher yet; there's no shipped
> Dockerfile to anchor on. I can help you translate the systemd gotchas to your
> own Docker setup, but treat this as best-effort: the gotchas below are the same
> ones that bite systemd deploys, recast for containers.

Then walk the relevant gotchas in Docker terms:

| Systemd gotcha | Docker translation |
|---|---|
| G1 `KEYRING_BACKEND` env | `ENV KEYRING_BACKEND=keyring.backends.null.Keyring` in Dockerfile, or `environment:` in compose |
| G2 cloudflared outbound | Run cloudflared as a sidecar container on a private network with the API; don't expose the API port to the host |
| G3 SQLite locking | Use `--workers 1` in CMD; don't scale via replica count for a single sqlite file |
| G4 `User=` perms | `USER patcher` in Dockerfile; ensure the volume mount is owned by that uid |
| G5 deploy token | Pass via env, not baked into the image |
| G6 restart loop | `docker logs` after `docker compose up` (no `-d`) for the real error |
| G7 first-boot ingest | Persistent volume for the SQLite file so ingest survives container restart |

For users without an existing Dockerfile, offer a starting-point scaffold with the
caveat that it's not part of the project. Don't write it into the repo; draft it
inline.

## Troubleshooting workflow

1. **Identify the input shape**: symptom or logs (or both).
2. **If logs**: grep for the signatures in the gotchas above; pattern-match and
   start there.
3. **If symptom**: pick the most likely gotcha; if multiple fit, ask for the most
   relevant log source.
4. **Don't propose a fix without confirming the gotcha is actually the cause.** If
   the user says "it's not that" twice, fall back to a general FastAPI/Linux
   diagnostic mindset.
5. **For Docker questions**: lead with the disclaimer, then translate.

## Troubleshooting output format

Keep responses scannable:

```
Likely cause: <Gotcha ID + short description>

Why I think so:
  <evidence from logs or symptom>

Fix:
  <concrete steps; commands inline>

If that doesn't resolve it, check:
  <2–3 less likely causes ranked by probability>
```

Read like a colleague triaging on a call, no "Patcher's API is designed to..."
preamble.

## What this skill does NOT do

- Does not modify the production system or the Healthchecks.io dashboard. All
  actions are recommendations the user runs themselves.
- Does not write a Dockerfile into the repo. Inline-only.
- Does not debug the Patcher *client* (`patcherctl` CLI on a Mac), a different
  surface with different gotchas.
- Does not diagnose Jamf Pro API issues (token, role, scoping).
- Does not propose architectural changes (Postgres instead of SQLite, k8s instead
  of systemd) unless the user explicitly asks about alternatives.
