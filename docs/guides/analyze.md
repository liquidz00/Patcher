---
description: "Filter and trend Patcher data by criterion. Covers the patcherctl analyze command, FilterCriteria and TrendCriteria values, and library equivalents."
---

(analyze)=

# Analyzing Data

:::{rst-class} lead
Filter, rank, and trend patch data to surface the titles that need attention.
:::

Two flavors: point it at a single Excel report for one-shot filtering, or trend across every cached dataset. Either way the goal is the same: tell you which titles are lagging and which are humming.

`patcherctl analyze` works against the latest exported report by default; pass an explicit Excel path to analyze a different one. From the library, call {meth}`PatcherClient.analyze <patcher.core.patcher_client.PatcherClient.analyze>` with a list of {class}`~patcher.core.models.patch.PatchTitle` objects.

## Criteria

Two criteria families drive analyze, used in different contexts:

- {class}`~patcher.core.analyze.FilterCriteria` for analyzing a **single** patch report
- {class}`~patcher.core.analyze.TrendCriteria` for analyzing patch data **over time**, comparing across multiple cached datasets

:::{tip}
Criteria names are case-insensitive and dash/underscore-flexible. `most-installed`, `most_installed`, and `MOST-INSTALLED` all resolve to the same option.
:::

### Filter criteria

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
| `installomator` | Titles that match an [Installomator](/guides/installomator) label. Helpful for identifying automation-ready software |

### Trend criteria

Requires at least two cached datasets to compare.

| Criteria | Description |
|---|---|
| `patch-adoption` | Completion rates over time for each software title |
| `release-frequency` | Frequency of updates per software title |
| `completion-trends` | Correlation between release dates and completion percentages |

## Options

| Flag | Library kwarg / method | Description |
|---|---|---|
| `--criteria X` | `criteria=X` (positional on `analyze` / `analyze_trend`) | Filter or trend criterion. Accepts the enum or its CLI string form. |
| `--top-n N` | `top_n=N` | Cap result size for top-N criteria. Ignored by `below-threshold` and `zero-completion` (those return all matching titles). |
| `--threshold X` | `threshold=X` | Completion-percent cutoff for `below-threshold`. Default `70.0`. |
| `--excel-file <path>` | call `analyze_excel(path, ...)` instead of `analyze(titles, ...)` | Operate on a specific Excel report rather than the latest cached one. |
| `--all-time` | call `analyze_trend(criterion, ...)` instead of `analyze(...)` | Switch from single-report filtering to trend analysis across every cached dataset. |
| `--summary` + `--output-dir <path>` | `save_to=<path>` (on `analyze_trend`) | Write an HTML version of the analysis alongside the printed table or returned DataFrame. |

## Examples

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

```console
$ patcherctl analyze --criteria below-threshold --threshold 50.0
$ patcherctl analyze --criteria most-installed
$ patcherctl analyze --criteria least-installed --top-n 5
$ patcherctl analyze --criteria recent-release
$ patcherctl analyze --criteria high-missing --top-n 10
$ patcherctl analyze --criteria installomator
```

To analyze a specific Excel file instead of the latest cached report:

```console
$ patcherctl analyze --excel-file /path/to/report.xlsx --criteria most-installed
```

Trend analysis across all cached datasets:

```console
$ patcherctl analyze --all-time --criteria patch-adoption
$ patcherctl analyze --all-time --criteria release-frequency
$ patcherctl analyze --all-time --criteria completion-trends
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
from patcher import FilterCriteria, PatcherClient

async with PatcherClient.from_state() as patcher:
    titles = await patcher.fetch_patches()

    # Threshold filter
    below = await patcher.analyze(titles, criteria=FilterCriteria.BELOW_THRESHOLD, threshold=50.0)

    # Top-N filter
    least = await patcher.analyze(titles, criteria=FilterCriteria.LEAST_INSTALLED, top_n=5)

    # CLI-style string also accepted
    high_missing = await patcher.analyze(titles, criteria="high-missing", top_n=10)
```

Filter a saved Excel report directly (skip `fetch_patches`):

```python
async with PatcherClient.from_state() as patcher:
    stale = await patcher.analyze_excel(
        "/path/to/report.xlsx",
        criteria="most-installed",
    )
```

Trend analysis across cached datasets returns a `pandas.DataFrame`:

```python
async with PatcherClient.from_state() as patcher:
    trend = await patcher.analyze_trend("patch-adoption")
    print(trend.head())
```

{meth}`analyze <patcher.core.patcher_client.PatcherClient.analyze>` accepts either the enum or its CLI string form and returns the filtered list of {class}`~patcher.core.models.patch.PatchTitle` objects. {meth}`analyze_excel <patcher.core.patcher_client.PatcherClient.analyze_excel>` operates on a specific Excel file instead of the latest cached report; {meth}`analyze_trend <patcher.core.patcher_client.PatcherClient.analyze_trend>` operates across cached datasets over time.
:::

::::

## Generating a summary

Pass `--summary` along with `--output-dir` (CLI) or `save_to=...` (library) to write an HTML version of the analysis alongside the stdout table or returned DataFrame. Summary files follow the naming pattern `patch-analysis-<date>.html` (or `trend-analysis-<criteria>.html` for trend analysis).

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

```console
$ patcherctl analyze --criteria below-threshold --threshold 80.0 --summary --output-dir ~/Reports
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
async with PatcherClient.from_state() as patcher:
    trend = await patcher.analyze_trend(
        "patch-adoption",
        save_to="~/Reports/trend-adoption.html",
    )
```

The DataFrame is returned regardless of whether `save_to` is provided. If the DataFrame is empty (e.g. no cached data matches the criterion), no file is written.
:::

::::

:::{tip}
`recent-release` pairs well with SLA / compliance reporting. Pull all patches released in the last week to confirm coverage against a 7-day SLA.
:::
