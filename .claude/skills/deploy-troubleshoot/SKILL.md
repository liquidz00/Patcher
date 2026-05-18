---
name: deploy-troubleshoot
description: |
  Diagnose deployment issues for the Patcher API service (`api/patcher_api/`).
  Accepts either a symptom description ("502 through cloudflared", "service won't
  start") or pasted logs (systemd journal, docker logs, uvicorn stderr) and walks
  the known failure modes. Knows the project-specific gotchas: `KEYRING_BACKEND`,
  cloudflared outbound-only model, SQLite locking under multi-worker uvicorn,
  systemd user/permission setup, deploy-token gating on `/admin/*`.

  Docker is not officially supported but the skill will help users debug their
  own Dockerfile by translating the systemd-based gotchas, with a clear caveat.

  Invoke when the user says: "/deploy-troubleshoot", "patcher api won't start",
  "502 from cloudflared", "keyring error on linux", "docker build issues with
  patcher api", "diagnose this log", or pastes a systemd / docker / uvicorn
  log and asks what's wrong.
---

# deploy-troubleshoot

Patcher's API service (`api/patcher_api/`) is the only piece intended to run on
a Linux host. The documented deploy is **uvicorn under systemd, fronted by a
cloudflared tunnel**. No inbound ports beyond 22/80/443 are opened. SQLite +
SQLAlchemy 2.0 async is the backing store. `/apps*` is public; `/admin/*` is
gated by a deploy-token.

This skill diagnoses deploy issues against that model. It also helps with Docker
deployments on a best-effort basis (see "Docker disclaimer" below).

## Input shapes

Accept either:

1. **Symptom description** - natural-language: "API returns 502 through
   cloudflared", "service won't start", "keyring import fails on boot", "admin
   endpoints return 401 with the right token".
2. **Pasted logs** - `journalctl -u patcher-api` output, `docker logs`,
   uvicorn stderr, cloudflared output.

If the user pastes logs without context, scan the logs first for the failure
signature (see the failure mode table below). If the user describes a symptom
without logs, ask for the most relevant log source as the next step, but offer
a likely diagnosis first based on the symptom alone.

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
- Public URL returns 502, but `curl http://localhost:8000/health` from the host works.
- `cloudflared tunnel info <tunnel>` shows the tunnel as connected.

**Fix path:**
1. Confirm uvicorn is bound to `127.0.0.1` (or `0.0.0.0`) and the port matches
   the cloudflared `ingress` config.
2. Confirm cloudflared is running on the same host (`systemctl status
   cloudflared`).
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

The systemd unit should run as a dedicated non-root user (e.g., `patcher-api`).
The SQLite db file's owner must match. If the service was bootstrapped as root
and `User=` was added later, the db file is unowned by the new user → service
crashes on write.

**Signature:**
```
sqlite3.OperationalError: attempt to write a readonly database
PermissionError: [Errno 13] Permission denied: '/var/lib/patcher-api/db.sqlite'
```

**Fix:**
```bash
chown -R patcher-api:patcher-api /var/lib/patcher-api/
chmod 0640 /var/lib/patcher-api/db.sqlite
```

### G5. `/admin/*` 401 with the deploy token

Admin routes require a deploy token (whatever the project's auth scheme calls
it; verify in `api/patcher_api/`'s auth module). Common causes of 401 with a
seemingly-correct token:

- Token has trailing whitespace from a copy-paste.
- Token was rotated but the client wasn't updated.
- Header is wrong (`Authorization: Bearer <token>` vs `X-Deploy-Token: <token>`;
  check the actual auth dep in `api/patcher_api/`).

**Fix path:**
1. Read the auth dependency in `api/patcher_api/` to confirm the header name.
2. `echo -n "<token>" | wc -c` and compare to the stored token length.
3. Confirm the env var holding the server-side token is loaded
   (`systemctl show patcher-api -p Environment`).

### G6. uvicorn restart loop under systemd

Systemd's default `Restart=on-failure` + a config error → tight restart loop
that masks the real error in `journalctl`.

**Signature:**
```
patcher-api.service: Main process exited, code=exited, status=1/FAILURE
patcher-api.service: Failed with result 'exit-code'.
patcher-api.service: Scheduled restart job, restart counter is at N.
```

**Fix path:**
1. `systemctl stop patcher-api`
2. Run the ExecStart command by hand as the service user; the real error
   surfaces immediately without the systemd wrapper.
3. Fix and `systemctl start` again.

### G7. ingest pipeline failures on first boot

The ingest pipeline (`api/patcher_api/ingest/`) populates the canonical apps DB
from Installomator labels, Homebrew Cask, AutoPkg. First-boot ingest can be
slow (minutes) and may fail silently if outbound network is blocked.

**Signature:**
- API starts, but `/apps` returns an empty list.
- No errors in journal.

**Fix path:**
1. Check ingest logs (location depends on how the project surfaces them).
2. Confirm outbound HTTPS works from the host.
3. Trigger a manual re-ingest via the admin endpoint.

## Docker disclaimer

**Docker is not an officially supported deploy path.** There's no canonical
Dockerfile in the repo. The user has flagged that they want to enable
self-hosting via Docker but can't support end-user Docker issues.

If the user is debugging a Docker deploy, lead with this:

> Docker isn't officially supported for Patcher yet; there's no shipped
> Dockerfile to anchor on. I can help you translate the systemd gotchas to
> your own Docker setup, but treat this as best-effort: the gotchas below
> are the same ones that bite systemd deploys, recast for containers.

Then walk the relevant gotchas in Docker terms:

| Systemd gotcha | Docker translation |
|---|---|
| G1 `KEYRING_BACKEND` env | `ENV KEYRING_BACKEND=keyring.backends.null.Keyring` in Dockerfile, or `environment:` in compose |
| G2 cloudflared outbound | Run cloudflared as a sidecar container on a private network with the API; don't expose the API port to the host |
| G3 SQLite locking | Use `--workers 1` in CMD; don't scale via replica count for a single sqlite file |
| G4 `User=` perms | `USER patcher-api` in Dockerfile; ensure the volume mount is owned by that uid |
| G5 deploy token | Pass via env, not baked into the image |
| G6 restart loop | `docker logs` after `docker compose up` (no `-d`) for the real error |
| G7 first-boot ingest | Persistent volume for the SQLite file so ingest survives container restart |

For users without an existing Dockerfile, offer a starting-point scaffold with
the caveat that it's not part of the project. Don't write it into the repo;
draft it inline.

## Workflow

1. **Identify the input shape**: symptom or logs (or both).
2. **If logs**: grep them for the signatures in the gotchas above. Pattern-match
   to the failure mode and start there.
3. **If symptom**: pick the most likely gotcha from the symptom; if multiple
   fit, ask the user for the most relevant log source.
4. **Don't propose a fix without checking the gotcha is actually the cause.**
   If the user says "it's not that" twice, fall back to a general FastAPI/Linux
   diagnostic mindset.
5. **For Docker questions**: lead with the disclaimer, then translate.

## Output format

Keep responses scannable. Use this shape:

```
Likely cause: <Gotcha ID + short description>

Why I think so:
  <evidence from logs or symptom>

Fix:
  <concrete steps; commands inline>

If that doesn't resolve it, check:
  <2–3 less likely causes ranked by probability>
```

Don't open with "Patcher's API is designed to..." or any other voice-rule-violating
preamble. Diagnostic responses should read like a colleague triaging on a call.

## What this skill does NOT do

- Does not touch the production system. All actions are recommendations the user
  runs themselves.
- Does not write a Dockerfile into the repo. Inline-only.
- Does not debug the Patcher *client* (`patcherctl` CLI on a Mac). That's a
  different surface with different gotchas.
- Does not diagnose Jamf Pro API issues (token, role, scoping). Those belong
  to the user's Jamf admin.
- Does not propose architectural changes (Postgres instead of SQLite, k8s
  instead of systemd). Stay inside the documented deploy model unless the user
  explicitly asks about alternatives.
