#!/usr/bin/env bash
#
# Patcher catalog swap. Invoked by systemd.path when the upload endpoint
# atomically renames a fresh DB into the watched filename.
#
# Flow (on failure at any step, alert via GitHub issue and rollback):
#   1. Stop patcher-api
#   2. Back up the live DB with a timestamped name
#   3. Move the incoming DB into the live path
#   4. Restore ownership + permissions
#   5. Start patcher-api
#   6. Prune backups older than PATCHER_BACKUP_RETENTION_DAYS
#
# Environment (read from /etc/patcher-api/env via systemd EnvironmentFile):
#   PATCHER_BACKUP_RETENTION_DAYS   default 14
#   PATCHER_ALERT_GITHUB_TOKEN      PAT with public_repo scope; empty disables alerts
#   PATCHER_ALERT_GITHUB_REPO       e.g. liquidz00/Patcher
#   PATCHER_ALERT_ON_SUCCESS        "true" to also open a success issue; default off

set -euo pipefail

# ---- Configuration ---------------------------------------------------------

LIVE_DB="${PATCHER_LIVE_DB:-/var/lib/patcher-api/patcher_api.db}"
INCOMING_DB="${PATCHER_INCOMING_DB:-/var/lib/patcher-api/incoming/patcher_api.db}"
BACKUP_DIR="${PATCHER_BACKUP_DIR:-/var/lib/patcher-api/backups}"
RETENTION_DAYS="${PATCHER_BACKUP_RETENTION_DAYS:-14}"
SERVICE="${PATCHER_API_SERVICE:-patcher-api.service}"
DB_USER="${PATCHER_DB_USER:-patcher}"
DB_GROUP="${PATCHER_DB_GROUP:-patcher}"
DB_MODE="${PATCHER_DB_MODE:-640}"

GITHUB_TOKEN="${PATCHER_ALERT_GITHUB_TOKEN:-}"
GITHUB_REPO="${PATCHER_ALERT_GITHUB_REPO:-}"
ALERT_ON_SUCCESS="${PATCHER_ALERT_ON_SUCCESS:-false}"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_PATH="${BACKUP_DIR}/patcher_api.db.${TIMESTAMP}.bak"
LOG_FILE=$(mktemp /tmp/patcher-swap.XXXXXX.log)

# Mirror everything we do to the log file so an alert has the full transcript.
exec > >(tee -a "$LOG_FILE") 2>&1

# ---- Alert helpers ---------------------------------------------------------

gather_context() {
    local label="$1"
    local journal
    journal=$(journalctl -u "$SERVICE" -n 30 --no-pager 2>&1 || echo "(journalctl read failed)")
    local disk
    disk=$(df -h "$(dirname "$LIVE_DB")" 2>&1 || echo "(df read failed)")
    local script_log
    script_log=$(cat "$LOG_FILE" 2>&1 || echo "(no script log)")

    cat <<EOF
**Status:** ${label}
**Host:** $(hostname)
**Timestamp:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Backup:** ${BACKUP_PATH}

### Script log

\`\`\`
${script_log}
\`\`\`

### journalctl -u ${SERVICE} -n 30

\`\`\`
${journal}
\`\`\`

### df -h $(dirname "$LIVE_DB")

\`\`\`
${disk}
\`\`\`
EOF
}

open_github_issue() {
    local title="$1"
    local body
    body=$(gather_context "$2")

    if [[ -z "$GITHUB_TOKEN" || -z "$GITHUB_REPO" ]]; then
        echo "[alert] GitHub credentials not configured; skipping issue creation"
        return 0
    fi

    # Build the JSON payload with python so we don't need jq and don't
    # have to worry about shell-escaping the body.
    local payload
    payload=$(
        TITLE="$title" BODY="$body" python3 -c '
import json, os, sys
print(json.dumps({
    "title": os.environ["TITLE"],
    "body": os.environ["BODY"],
    "labels": ["auto-alert", "catalog-swap"],
}))
'
    )

    # curl exit status not propagated by design. Alert failures should never
    # mask the underlying swap status to the operator.
    curl -fsS -X POST \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "https://api.github.com/repos/${GITHUB_REPO}/issues" \
        >/dev/null \
        && echo "[alert] GitHub issue opened: ${title}" \
        || echo "[alert] GitHub issue API call failed (alert lost)"
}

on_failure() {
    local exit_code=$?
    local failing_command="${BASH_COMMAND}"
    echo "[swap] FAILED on command: ${failing_command} (exit ${exit_code})"

    # Best-effort rollback: if we already moved the live DB to backup but
    # before restarting the service, try to restore so the API can come
    # back up while we investigate.
    if [[ -f "$BACKUP_PATH" && ! -f "$LIVE_DB" ]]; then
        echo "[swap] attempting rollback from ${BACKUP_PATH}"
        cp "$BACKUP_PATH" "$LIVE_DB" || echo "[swap] rollback copy failed"
        chown "${DB_USER}:${DB_GROUP}" "$LIVE_DB" || true
        chmod "$DB_MODE" "$LIVE_DB" || true
        systemctl start "$SERVICE" || true
    fi

    open_github_issue \
        "Patcher catalog swap FAILED on $(hostname) at ${TIMESTAMP}" \
        "FAILED at: ${failing_command} (exit ${exit_code})"

    exit "$exit_code"
}
trap on_failure ERR

# ---- Main swap -------------------------------------------------------------

echo "[swap] starting at ${TIMESTAMP}"
echo "[swap] live=${LIVE_DB} incoming=${INCOMING_DB} backup=${BACKUP_PATH}"

if [[ ! -f "$INCOMING_DB" ]]; then
    echo "[swap] incoming DB missing; nothing to do"
    exit 0
fi

mkdir -p "$BACKUP_DIR"

echo "[swap] stopping ${SERVICE}"
systemctl stop "$SERVICE"

if [[ -f "$LIVE_DB" ]]; then
    echo "[swap] backing up live DB to ${BACKUP_PATH}"
    mv "$LIVE_DB" "$BACKUP_PATH"
fi

echo "[swap] moving incoming DB into place"
mv "$INCOMING_DB" "$LIVE_DB"

echo "[swap] setting ownership ${DB_USER}:${DB_GROUP} mode ${DB_MODE}"
chown "${DB_USER}:${DB_GROUP}" "$LIVE_DB"
chmod "$DB_MODE" "$LIVE_DB"

echo "[swap] starting ${SERVICE}"
systemctl start "$SERVICE"

echo "[swap] pruning backups older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -maxdepth 1 -name "patcher_api.db.*.bak" -type f \
    -mtime "+${RETENTION_DAYS}" -print -delete || true

echo "[swap] complete"

if [[ "$ALERT_ON_SUCCESS" == "true" ]]; then
    open_github_issue \
        "Patcher catalog swap OK on $(hostname) at ${TIMESTAMP}" \
        "OK"
fi
