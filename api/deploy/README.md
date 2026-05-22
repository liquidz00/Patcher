# Patcher API deployment

Operational notes for the live Patcher API service on Linode. The systemd
units in this directory (`patcher-catalog-swap.path`, `.service`, and the
swap script) handle catalog refresh; this README covers the bits that
aren't expressed in those units.

## Environment file

Both the running API service and any operator scripts (notably
`grant_deploy_token.py`) read configuration from environment variables
prefixed with `PATCHER_API_`. On the Linode box, those live in:

```
/etc/patcher-api/env
```

The systemd unit pulls this in via `EnvironmentFile=`. **Operator scripts
do not** unless you source it explicitly. To run any maintenance script
against the live database state, source the env file first:

```bash
set -a
. /etc/patcher-api/env
set +a
```

`set -a` exports every variable defined for the rest of the shell session,
which is what pydantic-settings reads.

The most important variable is `PATCHER_API_DATABASE_URL`, which points at
the live SQLite file:

```
PATCHER_API_DATABASE_URL="sqlite+aiosqlite:////var/lib/patcher-api/patcher_api.db"
```

(Note the four slashes after `sqlite+aiosqlite:` — three for the URL scheme
separator plus the leading slash of the absolute path.)

## Minting a deploy token

Deploy tokens authorize the `/admin/catalog/upload` endpoint used by the
catalog-refresh GitHub Actions workflow. The mint script reads
`/etc/patcher-api/env` automatically at startup (via pydantic-settings,
same mechanism the service uses), so on the API host you don't need to
source the file or pass `--database-url`. The one permission requirement
is that the script must run as a user who can read that file. In practice
that means running as the `patcher` user via `sudo -u patcher`.

```bash
# Default 90-day expiry
sudo -u patcher /opt/patcher/.venv/bin/python \
    /opt/patcher/api/scripts/grant_deploy_token.py github-actions-runner

# Custom lifetime
sudo -u patcher /opt/patcher/.venv/bin/python \
    /opt/patcher/api/scripts/grant_deploy_token.py runner --expires-in-days 30

# Never-expires (use sparingly)
sudo -u patcher /opt/patcher/.venv/bin/python \
    /opt/patcher/api/scripts/grant_deploy_token.py runner --no-expiry
```

Copy the plaintext from stdout into the `PATCHER_DEPLOY_TOKEN` GitHub
Actions secret. The token is shown once and never persisted server-side
(only the SHA-256 hash hits the database).

Verify the row landed:

```bash
sudo sqlite3 /var/lib/patcher-api/patcher_api.db \
    "SELECT user_id, expires_at, revoked_at FROM deploy_tokens;"
```

### Overrides

`--database-url` and `PATCHER_API_DATABASE_URL` remain available for
local testing or non-standard setups. Precedence (highest to lowest):

1. `--database-url` flag
2. `PATCHER_API_DATABASE_URL` in the shell environment
3. The env file at the path resolved from `PATCHER_API_ENV_FILE`
   (defaults to `/etc/patcher-api/env`, auto-loaded if readable)
4. `.env` in the script's working directory
5. The relative default in `config.py` (triggers the warning below)

The env file path itself is overridable. Set `PATCHER_API_ENV_FILE` to
point at a different location if you've deployed to a non-standard
path or are running a fork with its own convention:

```bash
PATCHER_API_ENV_FILE=/opt/patcher/env sudo -u patcher \
    /opt/patcher/.venv/bin/python /opt/patcher/api/scripts/grant_deploy_token.py runner
```

### The relative-fallback warning

If none of the above sources provides a value, the script falls back to
the relative-path default in `api/patcher_api/config.py`
(`sqlite+aiosqlite:///./patcher_api.db`). That resolves against your
current working directory and writes the token to an orphaned SQLite
file that the systemd service will never read from. The script emits
a loud warning when this fallback fires; the symptom if it slips past
is a `401 Unauthorized` on `/admin/catalog/upload` despite a
fresh-looking secret.

The fix in production is almost always "run as the `patcher` user via
`sudo -u patcher` so the env file is readable." Locally, set
`PATCHER_API_DATABASE_URL` in your `.env` or pass `--database-url`
explicitly.

To inspect what the running service is configured against without
having to read the env file yourself:

```bash
sudo grep PATCHER_API_DATABASE_URL /etc/patcher-api/env
```

## Revoking a deploy token

```bash
sudo sqlite3 /var/lib/patcher-api/patcher_api.db \
    "UPDATE deploy_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE user_id = '<user>';"
```

Revoked tokens fail authentication immediately. To rotate, mint a fresh
token and update the GitHub Actions secret before revoking the old one.

## Catalog swap automation

The three systemd-related files in this directory implement the
upload-and-swap flow:

- `patcher-catalog-swap.path` — watches `/var/lib/patcher-api/incoming/patcher_api.db`
  for `PathChanged` events.
- `patcher-catalog-swap.service` — fires `swap-patcher-catalog.sh` when the
  path unit triggers.
- `swap-patcher-catalog.sh` — stops the API, backs up the live DB, moves
  the staged file into place, restarts the API, prunes old backups. On
  failure, attempts a best-effort rollback from the most recent backup
  and opens a GitHub issue summarizing the failure.

The catalog-refresh GitHub Actions workflow (`refresh-catalog.yml`)
streams the freshly-stitched DB to `POST /admin/catalog/upload`, which
writes it to the watched filename atomically. The path unit picks it up
and the swap script handles the rest.
