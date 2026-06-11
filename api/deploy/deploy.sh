#!/usr/bin/env bash
# Guarded deploy (pull, sync, migrate, restart). Run as root by patcher-deploy.service.
set -euo pipefail

REPO=/opt/patcher
ALEMBIC="$REPO/.venv/bin/alembic"
CODE_USER="${DEPLOY_CODE_USER:?set DEPLOY_CODE_USER in the env file}"  # owns the code + venv
DB_USER="${DEPLOY_DB_USER:-patcher}"                                  # owns the DB
UV="${DEPLOY_UV_BIN:?set DEPLOY_UV_BIN in the env file}"              # the code user's uv binary

# Wrapped so bash parses the whole file before `git reset` can rewrite it mid-run.
main() {
    code_home=$(getent passwd "$CODE_USER" | cut -d: -f6)
    # Code + venv steps run as their owner, with HOME set so git/uv find config + cache.
    as_code() { /usr/sbin/runuser -u "$CODE_USER" -- env HOME="$code_home" "$@"; }

    as_code git -C "$REPO" fetch --quiet origin main
    if [ -n "$(as_code git -C "$REPO" status --porcelain)" ]; then  # never clobber local changes
        echo "Deploy aborted: $REPO has uncommitted changes." >&2
        exit 1
    fi
    as_code git -C "$REPO" reset --hard origin/main
    as_code "$UV" sync --project "$REPO" --all-packages --all-extras --frozen

    # Migrations write the DB, so they run as the DB owner.
    /usr/sbin/runuser -u "$DB_USER" -- bash -c "cd '$REPO/api' && '$ALEMBIC' upgrade head"

    systemctl restart patcher-api.service
}

main "$@"
