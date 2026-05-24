---
description: "Detect cross-source version drift in the Patcher catalog. Covers patcherctl drift and PatcherClient.detect_drift."
---

(drift)=

# Detecting Drift

:::{rst-class} lead
Find apps where upstream patching sources disagree on what "latest" means. The strongest signal Patcher's stitched catalog can report.
:::

---

Every catalog source independently reports a current version for each app: Installomator's `appNewVersion`, Homebrew Cask's `version`. Most of the time they agree. When they don't, one source is probably silently stuck — the vendor moved their release artifact, the upstream label still finds the old location, and the tool keeps reporting the old version as latest indefinitely.

`patcherctl drift` surfaces these disagreements. Pair it with a weekly or monthly cadence and you'll catch silent failures upstream tools can't detect themselves.

## Sources that participate

Only sources that expose a stable per-app version string get compared:

| Source | Version field | Participates? |
|---|---|---|
| Installomator | `appNewVersion` | Yes |
| Homebrew Cask | `cask_json.version` | Yes |
| AutoPkg | _resolves at recipe run time, not in catalog_ | No |
| Mac App Store | _empirically negligible overlap with versioned sources_ | No |
| Jamf App Installers | _coverage indicator only_ | No |

Versions are compared via `packaging.Version` (so `4.32` and `4.32.0` are treated as equal — only meaningful disagreement counts as drift). Unparseable strings (Cask's date-style `2025-04-15`, Installomator's shell-expression `$(curl ...)`) get a case-insensitive string compare and a `parsed_ok=False` marker in the result.

## Options

| Flag | Library kwarg | Description |
|---|---|---|
| `--slug <slug>` | `slug="firefox"` | Inspect a single app. Mutually exclusive with `--vendor`/`--source`. |
| `--vendor <vendor>` | `vendor="Mozilla"` | Case-insensitive exact vendor match. List mode only. |
| `--source <source>` | `source="installomator"` | Require this source to be one of the disagreeing sources. List mode only. |
| `--limit <N>` | `limit=N` | Page size. Server caps at 1000. Default 100. |
| `--offset <N>` | `offset=N` | Entries to skip before the page. |
| `--format text\|json` | — | CLI-only. `json` emits a structured `DriftResponse` or `DriftEntry`. |

## Examples

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

Scan the whole catalog:

```console
$ patcherctl drift
```

Inspect one app:

```console
$ patcherctl drift --slug slack
```

Filter to one vendor:

```console
$ patcherctl drift --vendor Slack
```

Only entries where Installomator participates (most useful filter — if Installomator's label has stuck, this isolates it):

```console
$ patcherctl drift --source installomator
```

Pipe structured drift to another tool:

```console
$ patcherctl drift --format json | jq '.entries[] | select(.leader == "homebrew_cask")'
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
from patcher import PatcherClient

async with PatcherClient.from_state() as patcher:
    # List drift across the catalog
    response = await patcher.detect_drift()
    print(f"{response.total_with_drift} of {response.total_scanned} apps drifted")
    for entry in response.entries:
        leader = entry.leader or "unparseable"
        print(f"  {entry.slug}: leader={leader}")
        for v in entry.versions:
            print(f"    {v.source}: {v.version} ({'ok' if v.parsed_ok else '?'})")

    # Inspect one app
    one = await patcher.detect_drift(slug="slack")
    if one is None:
        print("Slack has no drift (or doesn't exist in the catalog).")
    else:
        print(f"Slack: {one.leader} is ahead of {one.laggard}")
```

Drop down to {class}`~patcher.clients.patcher_api.PatcherAPIClient` directly to skip the `PatcherClient` wrapper:

```python
from patcher import PatcherAPIClient

async with PatcherAPIClient() as api:
    response = await api.list_drift(vendor="Mozilla")
    one = await api.get_app_drift("firefox")
```

The catalog endpoints are public — no credentials required.
:::

::::

## What gets returned

A {class}`~patcher.clients.patcher_api.DriftEntry` carries the slug, name, vendor, every source's reported version, and a `leader`/`laggard` pair (the highest and lowest parsed versions). Both are `None` when any version couldn't be parsed; the raw versions are still in `versions` so you can render the disagreement without ordering it.

```python
DriftEntry(
    slug="slack",
    name="Slack",
    vendor="Slack",
    versions=[
        SourceVersion(source="installomator", version="4.32.0", parsed_ok=True),
        SourceVersion(source="homebrew_cask", version="4.40.0", parsed_ok=True),
    ],
    leader="homebrew_cask",
    laggard="installomator",
)
```

The list endpoint returns a {class}`~patcher.clients.patcher_api.DriftResponse` with `total_scanned` (apps with at least two versioned sources), `total_with_drift` (the filtered count of disagreements), and the page of entries.

:::{tip}
A weekly cron of `patcherctl drift --source installomator --format json` is a low-cost canary for "is my Installomator label set still pulling the right versions?" If the count creeps up unexpectedly, an upstream source moved.
:::
