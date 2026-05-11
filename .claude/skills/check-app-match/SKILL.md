---
name: check-app-match
description: |
  Given a Mac application name, enumerate every patching method that covers it across
  Installomator, Homebrew Cask, and AutoPkg, and surface the results as a structured
  per-ecosystem report. Read-only — no DB writes, no state changes. Useful when adding
  a new app to the canonical apps DB, debugging an unmatched patch title, or sanity-
  checking what's available before configuring deployment for a new title.

  Invoke when the user says any of: "check match for <app>", "what patching methods
  cover <app>", "is <app> in Installomator", "look up <app> across ecosystems", or
  similar phrasing. App name is the single required argument.
---

# check-app-match

Given an app name, this skill queries four ecosystems and prints a per-ecosystem
report of matching patching methods. It does not write to disk and does not require
Jamf Pro access (the App Installers ecosystem is intentionally skipped — see below).

## Required argument

A single Mac application name. Examples:

- `Google Chrome`
- `1Password`
- `Zoom`
- `Cisco AnyConnect Secure Mobility Client`

The app name is normalized (lowercase, strip spaces, strip dots) before matching,
but the original form is preserved in output. If the user gives a quoted form,
respect it.

## Workflow

Run these four checks in order. They're independent — failures in one don't block
the others. Report partial results if anything fails.

### 1. Installomator

Replicate Patcher's existing match algorithm (direct → normalized → fuzzy) against
Installomator's `Labels.txt`:

```bash
curl -fsSL https://raw.githubusercontent.com/Installomator/Installomator/refs/heads/main/Labels.txt > /tmp/installomator-labels.txt
```

Then run the matching via Patcher's installed venv (rapidfuzz is already in the
dev environment):

```bash
uv run python - <<'PY'
import sys
from rapidfuzz import fuzz, process

app_name = """<APP_NAME>"""  # substitute the user's input here

with open("/tmp/installomator-labels.txt") as f:
    labels = {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}

normalized = app_name.lower().replace(" ", "").replace(".", "")

direct = []
if app_name.lower() in labels:
    direct.append((app_name.lower(), 100, "direct"))
if normalized in labels and normalized != app_name.lower():
    direct.append((normalized, 100, "normalized"))

# Fuzzy: surface anything >= 75
fuzzy = []
for cand, score, _ in process.extract(normalized, labels, scorer=fuzz.ratio, limit=10):
    if score >= 75 and not any(cand == d[0] for d in direct):
        fuzzy.append((cand, score, "fuzzy"))

for name, score, kind in [*direct, *fuzzy]:
    if score == 100:
        flag = "exact"
    elif score >= 85:
        flag = "high conf"
    else:
        flag = "below threshold"
    print(f"  {name:<40} score {score:>3}  ({kind}, {flag})")
PY
```

If `Labels.txt` fetch fails, print:
```
  (Labels.txt unreachable; check network)
```

### 2. Homebrew Cask

Fetch the cask catalog JSON. It's ~1 MB — cache it under `/tmp` to avoid refetching
on repeat invocations within the same session:

```bash
test -f /tmp/cask.json || curl -fsSL https://formulae.brew.sh/api/cask.json > /tmp/cask.json
```

Filter the JSON for matches. The cask's `token` is the primary match key, but the
`name` array (a list of display names) is the secondary signal:

```bash
uv run python - <<'PY'
import json

app_name = """<APP_NAME>"""  # substitute the user's input here
normalized = app_name.lower().replace(" ", "-").replace(".", "")
name_lower = app_name.lower()

with open("/tmp/cask.json") as f:
    casks = json.load(f)

matches = []
for cask in casks:
    token = cask.get("token", "")
    names = [n.lower() for n in cask.get("name") or []]
    # Match: exact token, prefix token (for variants), or display-name in `name[]`
    if token == normalized or token.startswith(f"{normalized}-") or name_lower in names:
        matches.append({
            "token": token,
            "display": cask.get("name", [""])[0],
            "version": cask.get("version", ""),
            "deprecated": cask.get("deprecated", False),
            "disabled": cask.get("disabled", False),
        })

for m in matches:
    suffix = ""
    if m["deprecated"]:
        suffix += " [deprecated]"
    if m["disabled"]:
        suffix += " [disabled]"
    print(f"  {m['token']:<40} v{m['version']}{suffix}")

if not matches:
    print("  (no matches)")
PY
```

### 3. AutoPkg

**Try local first.** `autopkg search` is the fastest path when the tool is installed:

```bash
autopkg search "<APP_NAME>" 2>&1
```

Parse the table output — recipes appear with their parent repo. If `autopkg` is not
on `PATH` or the command fails with a non-zero exit code, fall back to GitHub code
search via `gh`:

```bash
gh api -X GET search/code -f q='<NORMALIZED_APP_NAME> in:path org:autopkg extension:recipe' --jq '.items[] | "\(.repository.full_name)/\(.path)"' | head -20
```

Notes:

- The local `autopkg search` returns recipes from all configured repos (typically
  more comprehensive than just `autopkg/*` org).
- The remote `gh` fallback only searches the `autopkg` GitHub org; community repos
  outside that org won't surface. Mention this caveat in the output.
- If both fail (no `autopkg`, no `gh`, or no network), print:
  ```
    (autopkg unreachable; install autopkg or gh CLI)
  ```

### 4. Jamf App Installers

**Skip with a note.** The undocumented `/api/v1/app-installers/titles` endpoint
requires Jamf Pro tenant access, which is not currently available.

Print:

```
  skipped — no Jamf access. Browse public catalog at:
  https://learn.jamf.com/r/en-US/jamf-app-catalog/App_Installers_Software_Titles
```

## Output format

After all four checks, emit a single consolidated report. Use the structure below
verbatim — fixed-width labels, two-space indent for results, blank line between
ecosystems:

```
App: <APP_NAME>
─────────────────────────────────────────────────────────────

Installomator
  <label-name>                             score <NN>  (direct|normalized|fuzzy, exact|high conf|below threshold)
  ...

Homebrew Cask
  <token>                                  v<version>[ deprecated][ disabled]
  ...

AutoPkg
  <recipe-path>                            (source: local | github-search)
  ...

Jamf App Installer
  skipped — no Jamf access. Browse public catalog at:
  https://learn.jamf.com/r/en-US/jamf-app-catalog/App_Installers_Software_Titles
```

If an ecosystem has no matches, print `(no matches)` indented in place of the
result list. If an ecosystem fails, print the failure note as above.

## Confidence-flag legend

For Installomator (the only ecosystem that uses fuzzy scoring):

| Score | Flag | Meaning |
|---|---|---|
| 100 | `exact` | Direct or normalized match — high signal |
| 85–99 | `high conf` | Above Patcher's default matching threshold |
| 75–84 | `below threshold` | Below the default threshold; surfaced for visibility but would NOT be picked up by `Installomator.match()` automatically |

## What this skill does NOT do

- Does not write to a database or any DB-style file. Read-only.
- Does not propose canonical-app-DB inserts. That's a separate skill for after
  the Patcher API DB schema lands.
- Does not validate that matched packages are still installable. Match quality
  is about identity, not freshness — the `Last-Verified-At` story belongs to the
  API DB layer, not this lookup utility.
- Does not require Jamf Pro tenant access. The App Installers ecosystem is
  explicitly skipped until tenant access is restored.

## Failure modes to handle gracefully

- **Labels.txt fetch fails** → print the unreachable note in the Installomator
  section; continue with the rest.
- **cask.json fetch fails** → print "(catalog unreachable)" in the Homebrew section.
- **Both autopkg + gh unavailable** → print the install note in the AutoPkg section.
- **rapidfuzz import fails** → user's venv isn't synced; print
  "(matching unavailable — run `make install-dev` to sync dev deps)" and skip the
  Installomator section.
- **No matches anywhere** → still emit the full report with `(no matches)` per
  ecosystem. The absence is itself useful information.
