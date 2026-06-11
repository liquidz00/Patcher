#!/usr/bin/env bash
# Guarded deploy (pull, sync, migrate, restart). Run as root; drops to patcher for unprivileged steps.
set -euo pipefail

REPO=/opt/patcher
VENV="$REPO/.venv"
APP_USER=patcher
UV="${UV_BIN:-uv}"  # set UV_BIN in the env file if uv isn't on root's PATH

# Wrapped so bash parses the whole file before `git reset` can rewrite it mid-run.
main() {
    app() { /usr/sbin/runuser -u "$APP_USER" -- "$@"; }

    app git -C "$REPO" fetch --quiet origin main
    if [ -n "$(app git -C "$REPO" status --porcelain)" ]; then  # never clobber local changes
        echo "Deploy aborted: $REPO has uncommitted changes." >&2
        exit 1
    fi
    app git -C "$REPO" reset --hard origin/main

    app "$UV" sync --project "$REPO" --all-packages --all-extras --frozen
    app bash -c "cd '$REPO/api' && '$VENV/bin/alembic' upgrade head"  # migrate as the DB owner

    systemctl restart patcher-api.service
}

main "$@"
