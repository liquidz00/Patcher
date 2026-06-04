#!/bin/bash

set -uo pipefail
fails=()

check() {  # name, url, body-substring (optional)
    local code
    code=$(curl -s -o /tmp/b -w '%{http_code}' --max-time 20 "$2" || echo 000)
    [[ "$code" =~ ^[23][0-9][0-9]$ ]] || { fails+=("$1 → HTTP $code"); return; }
    [[ -z "${3:-}" ]] || grep -q "$3" /tmp/b || fails+=("$1 → body missing '$3'")
}

check "api /health" https://api.patcherctl.dev/health '"status":"ok"'
check "mcp" https://mcp.patcherctl.dev/mcp
check "docs" https://docs.patcherctl.dev

if (( ${#fails[@]} )); then
    text="❌ Patcher monitor: ${#fails[@]} failing $(printf '%s\n' "${fails[@]}")"
    curl -s -X POST -H 'Content-type: application/json' --data "$(jq -nc --arg t "$text" '{text:$t}')" "$SLACK_WEBHOOK"
    exit 1
fi

echo "✅ all checks passed"
