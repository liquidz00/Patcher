---
description: "Compare patch state between two snapshots. Covers patcherctl diff and PatcherClient.diff."
---

(diff)=

# Diffing Snapshots

:::{rst-class} lead
Compare patch state across two points in time. Find what shifted, what regressed, and what's new.
:::

---

`patcherctl analyze --all-time` answers "how have things trended"; `patcherctl diff` answers "what changed between these two specific moments." Pair it with a scheduled export ([`automation`](/guides/automation)) and you have a paper trail of every patch-coverage change without standing up a separate observability stack.

Diff reuses the same `~/Library/Caches/Patcher/patch_data_*.pkl` snapshots that drive {doc}`analyze`, so it works against history Patcher has already been collecting; no extra opt-in.

## How snapshots are selected

| Flag | Meaning |
|---|---|
| _(none)_ | Fetch live patch data, compare against the most recent cached snapshot. |
| `--since <window>` | Live vs. the **earliest** cached snapshot inside the trailing window. `'30d'`, `'24h'`, `'1w'`. |
| `--all-time` | Live vs. the **earliest** cached snapshot ever. |
| `--no-fetch` | Skip the live fetch; compare the two most recent cached snapshots. Combine with `--since` or `--all-time` to widen the window. |
| `--between <from> <to>` | Two ISO dates (YYYY-MM-DD). Picks cached snapshots **closest** to each date. Implies `--no-fetch`. |

`--list-snapshots` prints every cached snapshot's timestamp and filename, then exits. Use it when you're not sure what's available.

:::{tip}
Snapshot timestamps come from filesystem mtime, not from the timestamp embedded in the cache filename (which is 12-hour and ambiguous). If you back up or move cache files, preserve mtimes.
:::

## Options

| Flag | Library kwarg | Description |
|---|---|---|
| `--since <window>` | `since=timedelta(days=30)` | Trailing window. CLI accepts `Nd`/`Nh`/`Nw`. |
| `--all-time` | `all_time=True` | Earliest snapshot ever. Mutually exclusive with `--since`. |
| `--between <from> <to>` | `between=(date_from, date_to)` | Two ISO dates. Cannot combine with `--since`, `--all-time`, or `--no-fetch`. |
| `--no-fetch` | `no_fetch=True` | Compare cached snapshots only. |
| `--list-snapshots` | — | CLI-only: print cache contents and exit. |
| `--format text\|json` | — | CLI-only: `text` (default) prints a table; `json` emits a structured {class}`~patcher.core.analyze.DiffResult` for piping. |

## Examples

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

Live vs. most recent cache:

```console
$ patcherctl diff
```

What's changed in the last 30 days?

```console
$ patcherctl diff --since 30d
```

What's changed since we first started tracking?

```console
$ patcherctl diff --all-time
```

Pick two specific dates from cache:

```console
$ patcherctl diff --between 2026-04-01 2026-05-01
```

Cache-only comparison (no live fetch, useful in CI):

```console
$ patcherctl diff --no-fetch --since 7d
```

Pipe structured output to another tool:

```console
$ patcherctl diff --since 30d --format json | jq '.version_bumps'
```

List what's cached:

```console
$ patcherctl diff --list-snapshots
Available cached snapshots (oldest → newest):
  2026-04-01T09:14:02  patch_data_04-01-26_09-14-02.pkl
  2026-04-15T09:13:55  patch_data_04-15-26_09-13-55.pkl
  2026-05-01T09:14:11  patch_data_05-01-26_09-14-11.pkl
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
from datetime import date, timedelta
from patcher import PatcherClient

async with PatcherClient.from_state() as patcher:
    # Live vs. most recent cache
    result = await patcher.diff()

    # Trailing 30 days
    result = await patcher.diff(since=timedelta(days=30))

    # Two specific cached dates
    result = await patcher.diff(
        between=(date(2026, 4, 1), date(2026, 5, 1)),
    )

    # Cache-only
    result = await patcher.diff(no_fetch=True, since=timedelta(days=7))

    print(f"{result.from_label} → {result.to_label}")
    print(f"added: {len(result.added)}, removed: {len(result.removed)}")
    for change in result.changed:
        print(f"  {change.title}: {change.from_completion_percent:.1f}% → {change.to_completion_percent:.1f}%")
```

Drop down to {class}`~patcher.core.analyze.Diff` directly for two snapshots you already have in hand (e.g. two `Path` objects, two `DataFrame` objects, two `list[PatchTitle]` objects):

```python
from patcher.core.analyze import Diff

result = Diff(from_titles, to_titles, from_label="2026-04-01", to_label="2026-05-01").compute()
```

{meth}`Diff.from_cache <patcher.core.analyze.Diff.from_cache>` picks two cached snapshots; {meth}`Diff.live_vs_cache <patcher.core.analyze.Diff.live_vs_cache>` compares a fresh fetch against cache. {meth}`PatcherClient.diff <patcher.core.patcher_client.PatcherClient.diff>` wraps both with flag validation.
:::

::::

## What gets compared

A title is **changed** if any of these differ between the two snapshots: completion percent, hosts patched, total hosts, or latest version. Released date and Installomator label changes are intentionally ignored (they tend to flip for upstream reasons unrelated to fleet state).

A {class}`~patcher.core.analyze.TitleChange` row carries both before/after values plus the deltas, so JSON consumers don't need to recompute.

## Output anatomy

The text formatter renders four sections:

```text
=== Compare: 2026-04-01 → 2026-05-01 ===

ADDED (3)
  Slack                  3.42.1   95.2%   189/198 hosts
  Microsoft Teams        24.5.2   88.1%   174/197 hosts
  ...

CHANGED (12)
  Firefox    138.0 → 139.0    72.1% → 91.4%  (+19.3)    142/197 → 180/197
  Chrome     136.0 → 137.0    91.2% → 88.0%  (-3.2)     179/196 → 173/197
  ...

REMOVED (1)
  Adobe Reader          (last seen 2026-04-01)

SUMMARY
  Titles tracked: 87 → 89  (+2)
  Avg completion delta: +4.2 pp
  Version bumps: 8
```

JSON output is a {class}`~patcher.core.analyze.DiffResult` dump; safe to feed directly to `jq`, `yq`, or any downstream Pydantic consumer.

:::{tip}
Pipe `--format json` into a daily Slack post or a status page; the `version_bumps` count is a clean leading indicator for "did upstream releases land in our fleet this week."
:::
