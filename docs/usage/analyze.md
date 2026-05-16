(analyze)=

# Analyze data

:::{rst-class} lead
Filter, rank, and trend patch data to surface the software titles that need attention.
:::

Analyze patch report data (either a single Excel report or trends across all cached datasets) to surface software titles that need attention.

`patcherctl analyze` works against the latest exported report by default; pass an explicit Excel path to analyze a different one. From the library, call {meth}`PatcherClient.analyze <patcher.core.patcher_client.PatcherClient.analyze>` with a list of {class}`~patcher.core.models.patch.PatchTitle` objects.

## Criteria

Two criteria families drive analyze, used in different contexts:

- {class}`~patcher.core.analyze.FilterCriteria` for analyzing a **single** patch report
- {class}`~patcher.core.analyze.TrendCriteria` for analyzing patch data **over time** (requires the `--all-time` flag on the CLI)

:::{note}
Criteria names are case-insensitive and dash/underscore-flexible. `most-installed`, `most_installed`, and `MOST-INSTALLED` all resolve to the same option.
:::

### Filter criteria

| Criteria | Description |
|---|---|
| `most-installed` | Software titles with the highest number of total installations |
| `least-installed` | Top 5 least-installed titles (use `--top-n` to change) |
| `oldest-least-complete` | Oldest patches with the lowest completion percent |
| `below-threshold` | Titles with completion below the specified `--threshold` |
| `recent-release` | Patches released in the last week |
| `zero-completion` | Titles with 0% completion |
| `top-performers` | Titles with completion above 90% |
| `high-missing` | Titles where missing patches are >50% of total hosts |
| `installomator` | Titles that match an [Installomator](/integrations/installomator) label. Helpful for identifying automation-ready software |

### Trend criteria

Requires `--all-time` and at least two cached datasets to compare.

| Criteria | Description |
|---|---|
| `patch-adoption` | Completion rates over time for each software title |
| `release-frequency` | Frequency of updates per software title |
| `completion-trends` | Correlation between release dates and completion percentages |

## Examples

::::{tab-set}

:::{tab-item} CLI
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
$ patcherctl analyze /path/to/report.xlsx --criteria most-installed
```

Trend analysis across all cached datasets:

```console
$ patcherctl analyze --all-time --criteria patch-adoption
$ patcherctl analyze --all-time --criteria release-frequency
$ patcherctl analyze --all-time --criteria completion-trends
```
:::

:::{tab-item} Library
:sync: library

```python
from patcher import FilterCriteria, PatcherClient

async with PatcherClient(client_id=..., client_secret=..., server=...) as patcher:
    titles = await patcher.fetch_patches()

    # Threshold filter
    below = await patcher.analyze(titles, criteria=FilterCriteria.BELOW_THRESHOLD, threshold=50.0)

    # Top-N filter
    least = await patcher.analyze(titles, criteria=FilterCriteria.LEAST_INSTALLED, top_n=5)

    # CLI-style string also accepted
    high_missing = await patcher.analyze(titles, criteria="high-missing", top_n=10)
```

`patcher.analyze()` accepts either a {class}`~patcher.core.analyze.FilterCriteria` enum member or its CLI string form. It returns the filtered list of {class}`~patcher.core.models.patch.PatchTitle` objects, ready for further processing, export, or storage.
:::

::::

## Generating a summary

Pass `--summary` along with `--output-dir` to generate an HTML report in addition to the stdout table. Summary files follow the naming pattern `patch-analysis-<date>.html` (or `trend-analysis-<criteria>.html` for trend analysis).

```console
$ patcherctl analyze --criteria below-threshold --threshold 80.0 --summary --output-dir ~/Reports
```

:::{tip}
`recent-release` pairs well with SLA / compliance reporting. Pull all patches released in the last week to confirm coverage against a 7-day SLA.
:::
