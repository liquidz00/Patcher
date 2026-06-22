---
description: "Every Patcher command from the patcherctl command line: export reports, analyze patch posture, diff snapshots, inspect catalog drift, and reset local state."
---

(cli-guides)=

# CLI

:::{rst-class} lead
Everything `patcherctl` can do, one subcommand at a time.
:::

---

`patcherctl` is the command-line interface of Patcher. Each section below covers one subcommand and the flags that shape its output. Every operation here has a library equivalent, see {doc}`library` if you would rather script it in Python.

::::{highlights}
{iconify}`octicon:terminal-16` No code required
: Generate reports, rank patch posture, and inspect drift straight from your terminal.

{iconify}`octicon:workflow-16` Built to automate
: Schedule exports straight into other tools.

{iconify}`octicon:key-16` Keychain-backed
: After a one-time setup, every subcommand uses your stored Jamf credentials.
::::

(export)=

## Export

Pulling patch data out of Jamf and into formats you can actually share. By default, a single invocation writes the patch report in all four formats (Excel, PDF, HTML, and JSON). If you only need one or two, narrowing the output is one option away.

### Options

`--path`, `-p` *(required)*
: Where to save the reports

`--format`, `-f`
: Restrict output to specific formats (`excel`, `pdf`, `html`, `json`). Pass multiple times on the CLI

`--sort`, `-s`
: Sort reports by a column

`--omit`, `-o`
: Skip patches released in the last 48 hours

`--date-format`, `-d`
: PDF header date format (see [Date format](#date-format) below)

`--ios`, `-m`
: Include iOS device data in reports (see [iOS device data](#ios))

`--concurrency`
: Max concurrent Jamf API requests *(Default: 5)*

`--device-details`, `-D`
: Per-title device sheets in the Excel export (slower on large fleets)

`--coverage`, `-c`
: Render an opt-in `Y`/`N` coverage column per source (`installomator`, `homebrew`, `autopkg`, `jai`). Pass multiple times. Sources disabled in your config are skipped with a notice unless `--force` is passed.

`--force`
: Force the requested `--coverage` sources on for this run, overriding your config (and the matching toggle).

`--homebrew` / `--no-homebrew`
: *(Deprecated)* Force Homebrew Cask matching on for this run. Configure integrations in setup, or use `--coverage` instead.

### Examples

```{code-block} bash
:caption: Write all four formats to a directory

$ patcherctl export --path ~/reports
```

```{code-block} bash
:caption: Only the formats you need

$ patcherctl export --path ~/reports --format html --format pdf
```

```{code-block} bash
:caption: Sorted, skipping anything released in the last 48 hours

$ patcherctl export --path ~/reports --sort "Released" --omit
```

```{code-block} bash
:caption: Add iOS device data and opt-in coverage columns

$ patcherctl export --path ~/reports --ios --coverage installomator --coverage homebrew
```

(date-format)=

### Date Format

The PDF header date format defaults to `Month-Day-Year` (e.g. `January 31 2026`). Available options:

| Option | Example |
|---|---|
| `Month-Year` | January 2026 |
| `Month-Day-Year` *(default)* | January 31 2026 |
| `Year-Month-Day` | 2026 April 21 |
| `Day-Month-Year` | 16 April 2026 |
| `Full` | Thursday September 26 2013 |

(concurrency)=

### Concurrency

Patcher fans out Jamf API requests in parallel, capped at 5 concurrent in-flight by default. Increase the cap for faster fetches on instances that can take the load, or lower it for tenants behind aggressive rate limiting.

:::{warning}
Cranking concurrency too high can starve other workloads on your Jamf server. **Stay at or below 5** unless you've coordinated with whoever owns the Jamf instance. See [Jamf's API scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices).
:::

(ios)=

### iOS Device Data

Passing `--ios` appends iOS / mobile device data to the report so you can see what's running on your fleet alongside the macOS patch coverage. Behind the scenes Patcher calls three Jamf APIs:

::::{steps}

:::{step} {meth}`~patcher.clients.jamf.JamfClient.get_device_ids`

Pulls the IDs of all enrolled mobile devices.
:::

:::{step} {meth}`~patcher.clients.jamf.JamfClient.get_device_os_versions`

Resolves each ID to its current OS version.
:::

:::{step} {meth}`~patcher.clients.jamf.JamfClient.get_sofa_feed`

Fetches the latest released iOS/iPadOS versions from [SOFA](https://sofa.macadmins.io/) to determine version recency.
:::
::::

The aggregate appears in the report as a count of mobile devices on the latest OS. Useful for the same SLA / compliance reporting workflows that drive `--omit` and the `recent-release` analyze criterion.

(homebrew)=

### Catalog Source Matching

Patcher matches each Jamf patch title against the Patcher API catalog across every source enabled in your `integrations` config (`installomator`, `homebrew`, `autopkg`, `jai`), all on by default. A source you disable in setup is no longer matched or recorded anywhere. [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) coverage, for example, picks up apps that carry no Installomator label.

The legacy `--homebrew` flag is deprecated: it now just force-enables Homebrew for a single run. Configure sources in setup instead, and use [`--coverage`](#export) to surface a source as a column in rendered reports.

(disabling_installomator_support)=

### Disabling Matching

If catalog matching doesn't fit your environment, turn it off entirely. When disabled, no catalog calls are made and the `sources` map on every {class}`~patcher.core.models.patch.PatchTitle` stays empty.

```{code-block} bash
:caption: Disabling catalog matching

$ defaults write \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist \
  enable_matching -bool false
```

(exported-field-policy)=
### Export Field Policy

```{include} _export-fields.md
```

(analyze)=

## Analyze

Filter, rank, and trend patch data to surface the titles that need attention.

Two flavors: point it at a single Excel report for one-shot filtering, or trend across every cached dataset. Either way the goal is to tell you which titles are lagging and which are humming.

:::{seealso}
For pairwise snapshot comparison (added/removed/changed titles between two specific points in time), see [Diff](#diff).
:::

By default, the analyze command works against the latest exported report. To analyze a different one, pass an explicit Excel path.

### Criteria

Two criteria families drive analyze, used in different contexts.

::::{markers}

:::{marker} {class}`~patcher.core.analyze.TitleFilter`
:icon: octicon:file-16
For analyzing a **single** patch report.
:::

:::{marker} {class}`~patcher.core.analyze.TrendAnalysis`
:icon: octicon:graph-16
For analyzing patch data **over time**, comparing across multiple cached datasets.
:::
::::

:::{admonition} Changed in version 3.0
:class: warning

The `FilterCriteria` and `TrendCriteria` enums and `Analyzer` dispatch wrapper were replaced with `TitleFilter` and `TrendAnalysis` classes. Each former enum value is now a method on the respective class, so library callers can do `TitleFilter(titles).most_installed(top_n=10)` directly. CLI strings (`--criteria most-installed`) and `PatcherClient.analyze("most-installed", ...)` still work, only the enum surface was removed.
:::

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0

:::{grid-item-card} Filter criteria
:class-card: outline

`most-installed`
: Software titles with the highest number of total installations

`least-installed`
: Top N least-installed titles (default 5)

`oldest-least-complete`
: Oldest patches with the lowest completion percent

`below-threshold`
: Titles with completion below the configured threshold (default 70%)

`recent-release`
: Patches released in the last week

`zero-completion`
: Titles with 0% completion

`top-performers`
: Titles with completion above 90%

`high-missing`
: Titles where missing patches are >50% of total hosts

`installomator`
: Titles that match an [Installomator](/project/sources) label
:::

:::{grid-item-card} Trend criteria
:class-card: outline

`patch-adoption`
: Completion rates over time for each software title

`release-frequency`
: Frequency of updates per software title

`completion-trends`
: Correlation between release dates and completion percentages
:::
::::

:::{tip}
CLI criteria names are dash-flexible: `most-installed` and `most_installed` both resolve. Library method names use the underscore form (`TitleFilter(titles).most_installed()`).
:::

### Options

`--criteria X`
: Filter or trend criterion. Accepts dash or underscore form

`--top-n N`
: Cap result size for top-N criteria. Ignored by `below-threshold` and `zero-completion` (those return all matching titles)

`--threshold X`
: Completion-percent cutoff for `below-threshold` *(Default 70.0)*

`--excel-file <path>`
: Operate on a specific Excel report rather than the latest cached one

`--all-time`
: Switch from single-report filtering to trend analysis across every cached dataset

`--summary` + `--output-dir <path>`
: Write an HTML version of the analysis alongside the printed table

### Examples

```{code-block} bash
:caption: Filter by a criterion

$ patcherctl analyze --criteria most-installed
```

```{code-block} bash
:caption: Set a completion threshold

$ patcherctl analyze --criteria below-threshold --threshold 50.0
```

```{code-block} bash
:caption: Cap the result size for top-N criteria

$ patcherctl analyze --criteria least-installed --top-n 5
```

```{code-block} bash
:caption: Analyze a specific Excel file instead of the latest cached report

$ patcherctl analyze --excel-file /path/to/report.xlsx --criteria most-installed
```

```{code-block} bash
:caption: Trend analysis across all cached datasets

$ patcherctl analyze --all-time --criteria patch-adoption
$ patcherctl analyze --all-time --criteria release-frequency
$ patcherctl analyze --all-time --criteria completion-trends
```

### Generating a Summary

Pass `--summary` along with `--output-dir` to write an HTML version of the analysis alongside the stdout table. Summary files follow the naming pattern `patch-analysis-<date>.html` (or `trend-analysis-<criteria>.html` for trend analysis).

```{code-block} bash
:caption: Generate HTML summary

$ patcherctl analyze \
  --criteria below-threshold \
  --threshold 80.0 \
  --summary \
  --output-dir ~/Reports
```

:::{tip}
`recent-release` pairs well with SLA / compliance reporting. Pull all patches released in the last week to confirm coverage against a 7-day SLA.
:::

### Output Anatomy

:::{definition} Fleet Compliance
Whole-fleet totals regardless of active filter used or passed to `patcherctl`
:::

A filter run leads with a Fleet Compliance panel then the matching titles as a table. Each completion percentage is color-coded by health: red below `--threshold`, yellow up to 90%, green at or above, so laggards stand out at a glance. A caption records the criteria and how many of the cached titles are shown.

```{code-block} text
:caption: Filter output: fleet summary panel, then the per-title table

╭──────────────────────────── Fleet Compliance ────────────────────────────╮
│ Titles 4    Avg completion 62.1%    Below 70% 2    Hosts patched 442/628 │
╰──────────────────────────────────────────────────────────────────────────╯
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ Title           ┃ Released    ┃ Patched ┃ Missing ┃ Version ┃ Completion % ┃ Total ┃ Label ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ Google Chrome   │ Apr 18 2026 │     188 │      12 │ 126.0   │        94.0% │   200 │   Y   │
├─────────────────┼─────────────┼─────────┼─────────┼─────────┼──────────────┼───────┼───────┤
│ Slack           │ Mar 14 2026 │     150 │      50 │ 4.38    │        75.0% │   200 │   Y   │
├─────────────────┼─────────────┼─────────┼─────────┼─────────┼──────────────┼───────┼───────┤
│ Mozilla Firefox │ Apr 02 2026 │      92 │      48 │ 128.0   │        65.7% │   140 │   Y   │
├─────────────────┼─────────────┼─────────┼─────────┼─────────┼──────────────┼───────┼───────┤
│ Zoom            │ Feb 20 2026 │      12 │      76 │ 6.1     │        13.6% │    88 │   N   │
└─────────────────┴─────────────┴─────────┴─────────┴─────────┴──────────────┴───────┴───────┘
criteria=most-installed  ·  showing 4 of 4 titles
```

(diff)=

## Diff

Compare patch state across two points in time. Find what shifted, what regressed, and what's new.

`patcherctl analyze --all-time` answers "how have things trended"; `patcherctl diff` answers "what changed between these two specific moments." Pair it with a scheduled export ([`automation`](/guides/automation)) and you have a paper trail of every patch-coverage change without standing up a separate observability stack.

Diff reuses the same `~/Library/Caches/Patcher/patch_data_*.parquet` snapshots that drive [Analyze](#analyze), so it works against history Patcher has already been collecting; no extra opt-in.

### How Snapshots Are Selected

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

### Options

`--since <window>`
: Trailing window. Accepts `Nd`/`Nh`/`Nw`

`--all-time`
: Earliest snapshot ever. Mutually exclusive with `--since`

`--between <from> <to>`
: Two ISO dates. Cannot combine with `--since`, `--all-time`, or `--no-fetch`

`--no-fetch`
: Compare cached snapshots only

`--list-snapshots`
: Print cache contents and exit

`--format text\|json`
: `text` (default) prints a table. `json` emits a structured {class}`~patcher.core.analyze.DiffResult` for piping

### Examples

```{code-block} bash
:caption: Live vs. most recent cache

$ patcherctl diff
```

```{code-block} bash
:caption: What's changed in the last 30 days

$ patcherctl diff --since 30d
```

```{code-block} bash
:caption: What's changed since we first started tracking

$ patcherctl diff --all-time
```

```{code-block} bash
:caption: Pick two specific dates from cache

$ patcherctl diff --between 2026-04-01 2026-05-01
```

```{code-block} bash
:caption: Cache-only comparison (no live fetch, useful in CI)

$ patcherctl diff --no-fetch --since 7d
```

```{code-block} bash
:caption: Pipe structured output to another tool

$ patcherctl diff --since 30d --format json | jq '.version_bumps'
```

```{code-block} bash
:caption: List what's cached

$ patcherctl diff --list-snapshots
Available cached snapshots (oldest → newest):
  2026-04-01T09:14:02  patch_data_202604010914.parquet
  2026-04-15T09:13:55  patch_data_202604150913.parquet
  2026-05-01T09:14:11  patch_data_202605010914.parquet
```

### What Gets Compared

A title is **changed** if completion percent, hosts patched, total hosts, or latest version differ between the two snapshots. Released date and Installomator label changes are intentionally ignored. A {class}`~patcher.core.analyze.TitleChange` row carries both before/after values plus the deltas, so consumers don't need to recompute.

### Output Anatomy

```{code-block} text
:caption: Text output: added, changed, removed, and a summary

Diff: snapshot-2026-04-01T09:14:02 → snapshot-2026-05-01T09:14:11
Added (2)
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Title           ┃ Released    ┃ Hosts ┃ Complete ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ Slack           │ Mar 14 2026 │ 190   │ 95.0%    │
│ Microsoft Teams │ Apr 02 2026 │ 176   │ 88.0%    │
└─────────────────┴─────────────┴───────┴──────────┘
Changed (2)
┏━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Title   ┃ Complete %    ┃ Hosts     ┃ Version              ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Firefox │ 72.1% → 91.4% │ 142 → 180 │ 138.0 → 139.0 (bump) │
│ Chrome  │ 91.2% → 88.0% │ 179 → 173 │ 137.0                │
└─────────┴───────────────┴───────────┴──────────────────────┘
Removed (1)
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Title        ┃ Last released ┃ Hosts ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Adobe Reader │ Apr 01 2026   │ 95    │
└──────────────┴───────────────┴───────┘
Summary
┌──────────────────┬─────────┐
│ Titles           │ 87 → 89 │
│ Unchanged        │ 74      │
│ Version bumps    │ 1       │
│ Avg completion Δ │ +4.20pp │
└──────────────────┴─────────┘
```

JSON output is a {class}`~patcher.core.analyze.DiffResult` dump; safe to feed directly to `jq`, `yq`, or any downstream Pydantic consumer.

:::{tip}
Pipe `--format json` into a daily Slack post or a status page; the `version_bumps` count is a clean leading indicator for "did upstream releases land in our fleet this week."
:::

(drift)=

## Drift

Find apps where upstream patching sources disagree on what "latest" means. The strongest signal Patcher's stitched catalog can report.

Every catalog source independently reports a current version for each app: Installomator's `appNewVersion`, Homebrew Cask's `version`. Most of the time they agree. When they don't, one source is probably silently stuck. The vendor moved their release artifact, the upstream label still finds the old location, and the tool keeps reporting the old version as latest indefinitely.

`patcherctl drift` surfaces these disagreements. Pair it with a weekly or monthly cadence and you'll catch silent failures upstream tools can't detect themselves.

### Sources That Participate

Only sources that expose a stable per-app version string get compared:

| Source | Version field | Participates? |
|---|---|---|
| Installomator | `appNewVersion` | Yes |
| Homebrew Cask | `cask_json.version` | Yes |
| AutoPkg | _resolves at recipe run time, not in catalog_ | No |
| Jamf App Installers | _coverage indicator only_ | No |

Versions are compared via `packaging.Version` (so `4.32` and `4.32.0` are treated as equal, only meaningful disagreement counts as drift). Unparseable strings (Cask's date-style `2025-04-15`, Installomator's shell-expression `$(curl ...)`) get a case-insensitive string compare and a `parsed_ok=False` marker in the result.

### Options

`--slug <slug>`
: Inspect a single app. Mutually exclusive with `--vendor`/`--source`

`--vendor <vendor>`
: Case-insensitive exact vendor match. List mode only

`--source <source>`
: Require this source to be one of the disagreeing sources. List mode only

`--limit <N>`
: Page size. Server caps at 1000 *(Default 100)*

`--offset <N>`
: Entries to skip before the page

`--format <text|json>`
: `json` emits a structured `DriftResponse` or `DriftEntry`

### Examples

```{code-block} bash
:caption: Scan the whole catalog

$ patcherctl drift
```

```{code-block} bash
:caption: Inspect one app

$ patcherctl drift --slug slack
```

```{code-block} bash
:caption: Filter to one vendor

$ patcherctl drift --vendor Slack
```

```{code-block} bash
:caption: Only entries where Installomator participates

$ patcherctl drift --source installomator
```

```{code-block} bash
:caption: Pipe structured drift to another tool

$ patcherctl drift \
  --format json | jq '.entries[] | select(.leader == "homebrew_cask")'
```

### What Gets Returned

Every catalog source independently reports a current version for each app (Installomator's `appNewVersion`, Homebrew Cask's `version`). When they disagree, one source is probably silently stuck. A {class}`~patcher.clients.patcher_api.DriftEntry` carries the slug, name, vendor, every source's reported version, and a `leader`/`laggard` pair (the highest and lowest parsed versions). Both are `None` when any version couldn't be parsed, the raw versions are still in `versions` so you can render the disagreement without ordering it.

The list endpoint returns a {class}`~patcher.clients.patcher_api.DriftResponse` with `total_scanned` (apps with at least two versioned sources), `total_with_drift` (the filtered count of disagreements), and the page of entries.

(reset)=
(resetting_patcher)=

## Reset

Controlling Patcher's state granularly.

The `reset` command restores specific configurations in Patcher. By default a **full reset** clears everything and re-runs the setup wizard. You can also reset individual components (credentials, UI settings, or cached data) without touching the rest.

:::{note}
Options are case-insensitive. `full`, `Full`, and `FULL` all work.
:::

### Options

`full`
: Credentials, UI config, setup state, and cache, then re-runs the setup wizard

`UI`
: PDF report appearance (header / footer text, font, optional logo)

`creds`
: Keychain credentials (URL, Client ID, Client Secret), all of them or just one

`cache`
: Cached patch data under `~/Library/Caches/Patcher`

:::{caution}
A full credential reset prompts for **all three** values (URL, Client ID, Client Secret). Only run it if you have access to the new credentials, particularly if your environment doesn't use SSO, or you originally relied on Patcher's automatic setup wizard.
:::

### Examples

::::{tab-set}

:::{tab-item} Full
:sync: full

```bash
$ patcherctl reset full
```

Resets everything and re-runs the setup wizard.
:::

:::{tab-item} UI
:sync: ui

```bash
$ patcherctl reset UI
```

Refreshes the appearance of generated reports (header / footer text or custom logos). Patcher will re-prompt for UI settings after the reset succeeds.
:::

:::{tab-item} Credentials
:sync: creds

Reset all three credentials:

```bash
$ patcherctl reset creds
```

Or scope to a single credential by name (one of `url`, `client_id`, `client_secret`):

```bash
$ patcherctl reset creds --credential url
```
:::

:::{tab-item} Cache
:sync: cache

```bash
$ patcherctl reset cache
```

Removes all cache files from the cache directory.
:::

::::

:::{seealso}
For more about cached data and where Patcher stores it, see {doc}`/project/data-storage`.
:::
