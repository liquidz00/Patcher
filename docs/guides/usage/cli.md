---
description: "Every Patcher command from the patcherctl command line: export reports, analyze patch posture, diff snapshots, inspect catalog drift, and reset local state."
---

(cli-guides)=

# CLI

:::{rst-class} lead
Everything `patcherctl` can do, one subcommand at a time.
:::

---

`patcherctl` is the command-line face of Patcher. Each section below covers one subcommand and the flags that shape its output. Every operation here has a library equivalent; see {doc}`library` if you would rather script it in Python.

(export)=

## Export

Pulling patch data out of Jamf and into formats you can actually share.

By default, a single invocation writes the patch report in all four formats: Excel, PDF, HTML, and JSON. If you only need one or two, narrowing the output is one option away.

### Options

| Flag | Library kwarg | Description |
|---|---|---|
| `--path`, `-p` | `output_dir=` | Where to save the reports (required) |
| `--format`, `-f` | `formats={...}` | Restrict output to specific formats (`excel`, `pdf`, `html`, `json`). Pass multiple times on the CLI |
| `--sort`, `-s` | `sort_by=` | Sort reports by a column |
| `--omit`, `-o` | `omit_recent_hours=48` | Skip patches released in the last 48 hours |
| `--date-format`, `-d` | `date_format=` | PDF header date format (see [Date format](#date-format) below) |
| `--ios`, `-m` | `include_ios=True` | Include iOS device data in reports (see [iOS device data](#ios)) |
| `--concurrency` | `concurrency=` | Max concurrent Jamf API requests. Default: `5` |
| `--device-details`, `-D` | `device_reports=` | Per-title device sheets in the Excel export (slower on large fleets) |
| `--homebrew` / `--no-homebrew` | `enable_homebrew=` / `match_homebrew=` | Also match titles against Homebrew Cask; adds a `Homebrew` coverage column (see [Homebrew matching](#homebrew)) |

### Examples

```bash
$ patcherctl export --path ~/reports
$ patcherctl export --path ~/reports --format excel
$ patcherctl export --path ~/reports --format html --format pdf
$ patcherctl export --path ~/reports --sort "Released"
$ patcherctl export --path ~/reports --omit
$ patcherctl export --path ~/reports --date-format "Month-Year"
$ patcherctl export --path ~/reports --ios
$ patcherctl export --path ~/reports --concurrency 10
$ patcherctl export --path ~/reports --device-details
$ patcherctl export --path ~/reports --homebrew
```

(date-format)=

### Date format

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

### Customizing report appearance

:::{important}
**UI configuration only applies to PDF and HTML formats.** Excel and JSON exports render correctly without any UI configuration. If you're only generating machine-readable reports, you can skip the UI setup entirely.

If you request a PDF export without configuring UI settings first, `patcherctl` will print a warning and continue with placeholder header / footer text. Run `patcherctl reset UI` to configure, or omit `pdf` from `--format`.
:::

PDF report styling (header text, footer text, custom font, logo, HTML header color) is configured via Patcher's property list. See {ref}`property_list_file` for the full plist schema, valid keys, and how to modify them.

A quick summary of what's customizable:

| Key | Affects |
|---|---|
| `header_text` | PDF + HTML report header |
| `footer_text` | PDF footer (page number is appended automatically) |
| `font_name`, `reg_font_path`, `bold_font_path` | PDF font (defaults to [Google's Assistant](https://fonts.google.com/specimen/Assistant)) |
| `logo_path` | PDF logo (PNG/JPEG/Pillow-supported formats) |
| `header_color` | HTML report header color (hex; falls back to `UIDefaults().header_color` when unset) |

`patcherctl reset UI` re-prompts for these settings interactively. See [Reset](#reset) for details.

(ios)=

### iOS device data

Passing `--ios` appends iOS / mobile device data to the report so you can see what's running on your fleet alongside the macOS patch coverage. Behind the scenes Patcher calls three Jamf APIs:

- {meth}`~patcher.clients.jamf.JamfClient.get_device_ids` pulls the IDs of all enrolled mobile devices.
- {meth}`~patcher.clients.jamf.JamfClient.get_device_os_versions` resolves each ID to its current OS version.
- {meth}`~patcher.clients.jamf.JamfClient.get_sofa_feed` fetches the latest released iOS/iPadOS versions from the [SOFA feed](https://sofa.macadmins.io/) to determine "on the latest" vs "behind."

The aggregate appears in the report as a count of mobile devices on the latest OS. Useful for the same SLA / compliance reporting workflows that drive `--omit` and the `recent-release` analyze criterion.

(homebrew)=

### Homebrew Cask matching

Patcher matches each Jamf patch title against the Installomator-sourced slugs in the Patcher API catalog. Passing `--homebrew` widens that to a second dimension: the catalog's [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) source, which covers apps that carry no Installomator label and exposes identity fields (bundle ID, canonical name) that labels often omit.

Matches keep their provenance. An Installomator hit lands in each title's `install_label`; a Homebrew Cask hit lands in the new `homebrew_cask` field; an app covered by both gets both. The Excel, PDF, and HTML reports surface this as a `Homebrew` column listing the matched cask token(s), and the JSON export carries the full structured matches under each title's `homebrew_cask` key.

The flag is off by default, so reports without it stay byte-for-byte unchanged. Homebrew matching rides on the same catalog pass as Installomator, so it has no effect when Installomator matching is turned off.

(disabling_installomator_support)=

### Disabling Installomator matching

If Installomator-style matching doesn't fit your environment, turn the catalog client off entirely. When disabled, no catalog calls are made and the `install_label` field on every {class}`~patcher.core.models.patch.PatchTitle` stays empty.

Patcher reads `enable_installomator` from its property list. Set it to `false`:

```bash
$ defaults write ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist enable_installomator -bool false
```

The next `patcherctl` invocation skips the catalog match entirely.

(analyze)=

## Analyze

Filter, rank, and trend patch data to surface the titles that need attention.

Two flavors: point it at a single Excel report for one-shot filtering, or trend across every cached dataset. Either way the goal is the same: tell you which titles are lagging and which are humming.

:::{seealso}
For pairwise snapshot comparison (added/removed/changed titles between two specific points in time), see [Diff](#diff).
:::

`patcherctl analyze` works against the latest exported report by default; pass an explicit Excel path to analyze a different one.

### Criteria

Two criteria families drive analyze, used in different contexts:

- {class}`~patcher.core.analyze.TitleFilter` for analyzing a **single** patch report
- {class}`~patcher.core.analyze.TrendAnalysis` for analyzing patch data **over time**, comparing across multiple cached datasets

```{versionchanged} 3.0
The `FilterCriteria` and `TrendCriteria` enums (plus the `Analyzer` dispatch wrapper) were replaced with `TitleFilter` and `TrendAnalysis`. Each former enum value is now a method on the respective class, so library callers can do `TitleFilter(titles).most_installed(top_n=10)` directly. CLI strings (`--criteria most-installed`) and `PatcherClient.analyze("most-installed", ...)` still work; only the enum surface was removed.
```

:::{tip}
CLI criteria names are dash-flexible: `most-installed` and `most_installed` both resolve. Library method names use the underscore form (`TitleFilter(titles).most_installed()`).
:::

#### Filter criteria

| Criteria | Description |
|---|---|
| `most-installed` | Software titles with the highest number of total installations |
| `least-installed` | Top N least-installed titles (default 5; configurable) |
| `oldest-least-complete` | Oldest patches with the lowest completion percent |
| `below-threshold` | Titles with completion below the configured threshold (default 70%) |
| `recent-release` | Patches released in the last week |
| `zero-completion` | Titles with 0% completion |
| `top-performers` | Titles with completion above 90% |
| `high-missing` | Titles where missing patches are >50% of total hosts |
| `installomator` | Titles that match an [Installomator](/project/sources) label. Helpful for identifying automation-ready software |

#### Trend criteria

Requires at least two cached datasets to compare.

| Criteria | Description |
|---|---|
| `patch-adoption` | Completion rates over time for each software title |
| `release-frequency` | Frequency of updates per software title |
| `completion-trends` | Correlation between release dates and completion percentages |

### Options

| Flag | Library kwarg / method | Description |
|---|---|---|
| `--criteria X` | `criteria="X"` (string on `analyze` / `analyze_trend`), or `TitleFilter(titles).X(...)` directly | Filter or trend criterion. CLI accepts dash or underscore form; library methods use the underscore form. |
| `--top-n N` | `top_n=N` | Cap result size for top-N criteria. Ignored by `below-threshold` and `zero-completion` (those return all matching titles). |
| `--threshold X` | `threshold=X` | Completion-percent cutoff for `below-threshold`. Default `70.0`. |
| `--excel-file <path>` | call `analyze_excel(path, ...)` instead of `analyze(titles, ...)` | Operate on a specific Excel report rather than the latest cached one. |
| `--all-time` | call `analyze_trend(criterion, ...)` instead of `analyze(...)` | Switch from single-report filtering to trend analysis across every cached dataset. |
| `--summary` + `--output-dir <path>` | `save_to=<path>` (on `analyze_trend`) | Write an HTML version of the analysis alongside the printed table or returned DataFrame. |

### Examples

```bash
$ patcherctl analyze --criteria below-threshold --threshold 50.0
$ patcherctl analyze --criteria most-installed
$ patcherctl analyze --criteria least-installed --top-n 5
$ patcherctl analyze --criteria recent-release
$ patcherctl analyze --criteria high-missing --top-n 10
$ patcherctl analyze --criteria installomator
```

To analyze a specific Excel file instead of the latest cached report:

```bash
$ patcherctl analyze --excel-file /path/to/report.xlsx --criteria most-installed
```

Trend analysis across all cached datasets:

```bash
$ patcherctl analyze --all-time --criteria patch-adoption
$ patcherctl analyze --all-time --criteria release-frequency
$ patcherctl analyze --all-time --criteria completion-trends
```

### Generating a summary

Pass `--summary` along with `--output-dir` to write an HTML version of the analysis alongside the stdout table. Summary files follow the naming pattern `patch-analysis-<date>.html` (or `trend-analysis-<criteria>.html` for trend analysis).

```bash
$ patcherctl analyze --criteria below-threshold --threshold 80.0 --summary --output-dir ~/Reports
```

:::{tip}
`recent-release` pairs well with SLA / compliance reporting. Pull all patches released in the last week to confirm coverage against a 7-day SLA.
:::

(diff)=

## Diff

Compare patch state across two points in time. Find what shifted, what regressed, and what's new.

`patcherctl analyze --all-time` answers "how have things trended"; `patcherctl diff` answers "what changed between these two specific moments." Pair it with a scheduled export ([`automation`](/guides/automation)) and you have a paper trail of every patch-coverage change without standing up a separate observability stack.

Diff reuses the same `~/Library/Caches/Patcher/patch_data_*.pkl` snapshots that drive [Analyze](#analyze), so it works against history Patcher has already been collecting; no extra opt-in.

### How snapshots are selected

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

| Flag | Library kwarg | Description |
|---|---|---|
| `--since <window>` | `since=timedelta(days=30)` | Trailing window. CLI accepts `Nd`/`Nh`/`Nw`. |
| `--all-time` | `all_time=True` | Earliest snapshot ever. Mutually exclusive with `--since`. |
| `--between <from> <to>` | `between=(date_from, date_to)` | Two ISO dates. Cannot combine with `--since`, `--all-time`, or `--no-fetch`. |
| `--no-fetch` | `no_fetch=True` | Compare cached snapshots only. |
| `--list-snapshots` | — | CLI-only: print cache contents and exit. |
| `--format text\|json` | — | CLI-only: `text` (default) prints a table; `json` emits a structured {class}`~patcher.core.analyze.DiffResult` for piping. |

### Examples

Live vs. most recent cache:

```bash
$ patcherctl diff
```

What's changed in the last 30 days?

```bash
$ patcherctl diff --since 30d
```

What's changed since we first started tracking?

```bash
$ patcherctl diff --all-time
```

Pick two specific dates from cache:

```bash
$ patcherctl diff --between 2026-04-01 2026-05-01
```

Cache-only comparison (no live fetch, useful in CI):

```bash
$ patcherctl diff --no-fetch --since 7d
```

Pipe structured output to another tool:

```bash
$ patcherctl diff --since 30d --format json | jq '.version_bumps'
```

List what's cached:

```bash
$ patcherctl diff --list-snapshots
Available cached snapshots (oldest → newest):
  2026-04-01T09:14:02  patch_data_04-01-26_09-14-02.pkl
  2026-04-15T09:13:55  patch_data_04-15-26_09-13-55.pkl
  2026-05-01T09:14:11  patch_data_05-01-26_09-14-11.pkl
```

### What gets compared

A title is **changed** if any of these differ between the two snapshots: completion percent, hosts patched, total hosts, or latest version. Released date and Installomator label changes are intentionally ignored (they tend to flip for upstream reasons unrelated to fleet state).

A {class}`~patcher.core.analyze.TitleChange` row carries both before/after values plus the deltas, so JSON consumers don't need to recompute.

### Output anatomy

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

(drift)=

## Drift

Find apps where upstream patching sources disagree on what "latest" means. The strongest signal Patcher's stitched catalog can report.

Every catalog source independently reports a current version for each app: Installomator's `appNewVersion`, Homebrew Cask's `version`. Most of the time they agree. When they don't, one source is probably silently stuck. The vendor moved their release artifact, the upstream label still finds the old location, and the tool keeps reporting the old version as latest indefinitely.

`patcherctl drift` surfaces these disagreements. Pair it with a weekly or monthly cadence and you'll catch silent failures upstream tools can't detect themselves.

### Sources that participate

Only sources that expose a stable per-app version string get compared:

| Source | Version field | Participates? |
|---|---|---|
| Installomator | `appNewVersion` | Yes |
| Homebrew Cask | `cask_json.version` | Yes |
| AutoPkg | _resolves at recipe run time, not in catalog_ | No |
| Mac App Store | _empirically negligible overlap with versioned sources_ | No |
| Jamf App Installers | _coverage indicator only_ | No |

Versions are compared via `packaging.Version` (so `4.32` and `4.32.0` are treated as equal, only meaningful disagreement counts as drift). Unparseable strings (Cask's date-style `2025-04-15`, Installomator's shell-expression `$(curl ...)`) get a case-insensitive string compare and a `parsed_ok=False` marker in the result.

### Options

| Flag | Library kwarg | Description |
|---|---|---|
| `--slug <slug>` | `slug="firefox"` | Inspect a single app. Mutually exclusive with `--vendor`/`--source`. |
| `--vendor <vendor>` | `vendor="Mozilla"` | Case-insensitive exact vendor match. List mode only. |
| `--source <source>` | `source="installomator"` | Require this source to be one of the disagreeing sources. List mode only. |
| `--limit <N>` | `limit=N` | Page size. Server caps at 1000. Default 100. |
| `--offset <N>` | `offset=N` | Entries to skip before the page. |
| `--format text\|json` | — | CLI-only. `json` emits a structured `DriftResponse` or `DriftEntry`. |

### Examples

Scan the whole catalog:

```bash
$ patcherctl drift
```

Inspect one app:

```bash
$ patcherctl drift --slug slack
```

Filter to one vendor:

```bash
$ patcherctl drift --vendor Slack
```

Only entries where Installomator participates (most useful filter; if Installomator's label has stuck, this isolates it):

```bash
$ patcherctl drift --source installomator
```

Pipe structured drift to another tool:

```bash
$ patcherctl drift --format json | jq '.entries[] | select(.leader == "homebrew_cask")'
```

### What gets returned

A {class}`~patcher.clients.patcher_api.DriftEntry` carries the slug, name, vendor, every source's reported version, and a `leader`/`laggard` pair (the highest and lowest parsed versions). Both are `None` when any version couldn't be parsed; the raw versions are still in `versions` so you can render the disagreement without ordering it.

The list endpoint returns a {class}`~patcher.clients.patcher_api.DriftResponse` with `total_scanned` (apps with at least two versioned sources), `total_with_drift` (the filtered count of disagreements), and the page of entries.

:::{tip}
A weekly cron of `patcherctl drift --source installomator --format json` is a low-cost canary for "is my Installomator label set still pulling the right versions?" If the count creeps up unexpectedly, an upstream source moved.
:::

(reset)=
(resetting_patcher)=

## Reset

Controlling Patcher's state granularly.

The `reset` command restores specific configurations in Patcher. By default a **full reset** clears everything and re-runs the setup wizard. You can also reset individual components (credentials, UI settings, or cached data) without touching the rest.

:::{note}
Options are case-insensitive. `full`, `Full`, and `FULL` all work.
:::

### Options

| Option | What it resets |
|---|---|
| `full` | Credentials, UI config, setup state, and cache, then re-runs the setup wizard |
| `UI` | PDF report appearance (header / footer text, font, optional logo) |
| `creds` | Keychain credentials (URL, Client ID, Client Secret), all of them or just one |
| `cache` | Cached patch data under `~/Library/Caches/Patcher` |

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
