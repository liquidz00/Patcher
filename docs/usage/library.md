---
description: "PatcherClient library reference. Method-by-method coverage of from_state, fetch_patches, analyze, analyze_trend, export, reset, and aclose."
---

(library)=

# Library Reference

:::{rst-class} lead
The full surface of {class}`~patcher.PatcherClient` for callers using Patcher as a Python library instead of (or alongside) the `patcherctl` CLI.
:::

Every method on `PatcherClient` is async. The recommended pattern is `async with PatcherClient(...) as patcher:` so connection pools (Jamf + Patcher API) close cleanly on exit. The {doc}`/getting-started/setup` library tab covers construction; this page is the method-by-method reference.

## `from_state` (classmethod)

```python
@classmethod
def from_state(cls, **overrides) -> "PatcherClient":
```

Construct a client using state already persisted on this Mac — credentials from the macOS keychain, UI customization and `enable_installomator` from the plist. The library equivalent of `patcherctl` picking up where the last invocation left off. No constructor arguments to repeat; pass any kwarg as an override.

**Typical use**

```python
from patcher import PatcherClient

async with PatcherClient.from_state() as patcher:
    titles = await patcher.fetch_patches()
    await patcher.export(titles, output_dir="~/reports", formats={"pdf"})
```

**Overrides**

Common kwargs to pass through:

- `concurrency=10` — bump the Jamf request ceiling for this invocation.
- `debug=True` — enable verbose logging.
- `disable_cache=True` — skip on-disk patch-data caching.
- `enable_installomator=False` — explicitly opt out of catalog matching even if the plist says yes.

**Caveats**

- Requires that `patcherctl` has completed its setup wizard on this Mac. If keychain credentials are missing, the underlying Jamf calls will raise `CredentialError` at first use.
- Reads happen at construction time; if you change keychain or plist values during a long-running process, re-instantiate to pick them up.

## `fetch_patches`

```python
async def fetch_patches(
    self,
    *,
    match_installomator: bool = True,
    include_ios: bool = False,
    sort_by: str | None = None,
    omit_recent_hours: int | None = None,
) -> list[PatchTitle]:
```

The library equivalent of the CLI's `export` flow up to the point of writing files. Composes the pipeline: Jamf policies → patch summaries → optional Installomator matching → optional iOS append → optional sort/filter.

**Typical use**

```python
async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
) as patcher:
    titles = await patcher.fetch_patches()
    print(f"{len(titles)} patch titles ({sum(1 for t in titles if t.install_label)} matched)")
```

**Parameters**

`match_installomator`
: When `True` (default), each title is matched against the Patcher API's stitched catalog and titles with an Installomator label get their `install_label` populated. No-op when the client was constructed with `enable_installomator=False`.

`include_ios`
: Append per-iOS-version summaries to the returned list. Costs additional Jamf API calls for each policy that targets iOS.

`sort_by`
: Sort the returned list by an attribute of {class}`~patcher.core.models.patch.PatchTitle` (e.g. `"released"`, `"completion_percent"`). Name is normalized to lowercase + underscores.

`omit_recent_hours`
: Drop titles released within the past N hours. Mirrors the CLI's `--omit` flag — useful for ignoring brand-new releases that haven't had time to roll out yet.

**Caveats**

- `match_installomator=True` requires network access to `api.patcherctl.dev`. If the API is unreachable, matching silently fails and `install_label` stays empty on every title; no exception is raised.
- `sort_by` validates against `PatchTitle`'s attribute set and raises {class}`~patcher.PatcherError` for unknown names.

## `analyze`

```python
async def analyze(
    self,
    titles: list[PatchTitle],
    criteria: FilterCriteria | str,
    *,
    threshold: float | None = 70.0,
    top_n: int | None = None,
) -> list[PatchTitle]:
```

Filter and sort patch titles by a named criterion. Accepts either a {class}`~patcher.FilterCriteria` enum value or a CLI-style string (`"most-installed"`, `"below-threshold"`, etc.).

**Typical use**

```python
from patcher import PatcherClient, FilterCriteria

async with PatcherClient(...) as patcher:
    titles = await patcher.fetch_patches()
    top_five = await patcher.analyze(titles, FilterCriteria.MOST_INSTALLED, top_n=5)
    behind = await patcher.analyze(titles, "below-threshold", threshold=50.0)
```

**Parameters**

`titles`
: Patch titles to analyze. Typically the output of `fetch_patches()`.

`criteria`
: Filter/sort criterion. See {class}`~patcher.FilterCriteria` for the full list of values and their CLI string equivalents.

`threshold`
: Completion-percent threshold for the `below_threshold` criterion. Ignored by other criteria. Defaults to `70.0`.

`top_n`
: When set, return at most N results. The `below_threshold` and `zero_completion` criteria ignore this (they always return every matching title).

## `analyze_excel`

```python
async def analyze_excel(
    self,
    excel_path: str | Path,
    criteria: FilterCriteria | str,
    *,
    threshold: float | None = 70.0,
    top_n: int | None = None,
) -> list[PatchTitle]:
```

Filter a saved Patcher Excel report instead of an in-memory list. Library equivalent of `patcherctl analyze --excel-file`.

**Typical use**

```python
async with PatcherClient.from_state() as patcher:
    stale = await patcher.analyze_excel(
        "~/reports/patch-report-05-18-26.xlsx",
        criteria="below-threshold",
        threshold=50.0,
    )
```

## `analyze_trend`

```python
async def analyze_trend(
    self,
    criteria: TrendCriteria | str,
    *,
    save_to: str | Path | None = None,
):
```

Compute a trend analysis across every cached patch dataset. Library equivalent of `patcherctl analyze --all-time`. Returns a `pandas.DataFrame`.

**Typical use**

```python
async with PatcherClient.from_state() as patcher:
    trend = await patcher.analyze_trend("patch-adoption", save_to="~/reports/trend.html")
    print(trend.head())
```

**Parameters**

`criteria`
: One of the trend criteria — `"patch-adoption"`, `"release-frequency"`, `"completion-trends"` (or the enum form from {class}`~patcher.TrendCriteria`).

`save_to`
: Optional path. When set, the DataFrame is also written as HTML. Parent directories are created as needed. The return value is unchanged regardless of `save_to`.

**Caveats**

- Reads from the cached datasets in `~/Library/Caches/Patcher/`. Returns an empty DataFrame when the cache is empty or no snapshot matches the requested criterion.

## `export`

```python
async def export(
    self,
    titles: list[PatchTitle],
    *,
    output_dir: str | Path,
    formats: set[str] | None = None,
    report_title: str | None = None,
    date_format: str = "%B %d %Y",
    header_color: str | None = "#6432bdff",
    analysis: bool = False,
    device_reports: dict[str, list] | None = None,
) -> dict[str, str]:
```

Write patch titles to one or more report formats on disk. Returns a `{format: output_path}` dict.

**Typical use**

```python
async with PatcherClient(...) as patcher:
    titles = await patcher.fetch_patches()
    written = await patcher.export(
        titles,
        output_dir="~/reports",
        formats={"pdf", "json"},
        report_title="June Patch Report",
    )
    for fmt, path in written.items():
        print(f"{fmt}: {path}")
```

**Parameters**

`titles`
: Patch titles to include. Typically straight from `fetch_patches()`, optionally filtered by `analyze()`.

`output_dir`
: Directory to write report files into. Created if missing.

`formats`
: Subset of `{"excel", "html", "pdf", "json"}`. Defaults to all four.

`report_title`
: Header text on the PDF/HTML reports. Falls back to the `ui_config`'s `HEADER_TEXT` value, then to `"Patch Report"`.

`date_format`
: Strftime format for date headers on PDF/HTML reports. Defaults to `"%B %d %Y"` (e.g. `"June 03 2026"`).

`header_color`
: Hex color for the HTML report's header banner. Defaults to Patcher purple (`#6432bdff`).

`analysis`
: When `True`, the report is treated as an analysis output rather than a full export. Affects the HTML file naming so analysis runs don't clobber the daily export.

`device_reports`
: Optional per-title device detail data, keyed by `title_id`. Excel uses this to add a per-title sheet of devices missing each patch. Get this from {meth}`~patcher.JamfClient.get_title_reports` if you want it.

## `reset`

```python
async def reset(
    self,
    kind: Literal["full", "UI", "creds", "cache"],
    *,
    credential: Literal["url", "client_id", "client_secret"] | None = None,
) -> None:
```

Reset persisted state. Library equivalent of `patcherctl reset <kind>`. Unlike the CLI, `reset` does **not** re-launch the setup wizard after a `"full"` reset — library callers re-construct a `PatcherClient` themselves when ready.

**Typical use**

```python
async with PatcherClient.from_state() as patcher:
    # Just wipe the patch-data cache between runs:
    await patcher.reset("cache")

    # Rotate a single credential:
    await patcher.reset("creds", credential="client_secret")
```

**Kinds**

- `"cache"` — empty `~/Library/Caches/Patcher/`. Works in any mode (keychain-backed or in-memory credentials).
- `"creds"` — delete Jamf credentials from the keychain. Pass `credential=` to scope to one. Requires keychain-backed mode.
- `"UI"` — clear UI customization from the plist. Requires keychain-backed mode.
- `"full"` — every reset above, plus clears `setup_completed` so the next `patcherctl` invocation re-runs the wizard. Requires keychain-backed mode.

**Caveats**

- `"creds"`, `"UI"`, and `"full"` raise {class}`~patcher.PatcherError` when called on a client constructed with in-memory credentials. There's nothing on disk to reset in that mode.

## `aclose`

```python
async def aclose(self) -> None:
```

Release the underlying httpx connection pools for both `jamf` and `api`. Idempotent — calling twice is safe.

You don't usually need to call this directly. `async with PatcherClient(...) as patcher:` handles it on exit:

```python
async with PatcherClient(...) as patcher:
    titles = await patcher.fetch_patches()
# Connection pools released here, even if fetch_patches raised.
```

Call it explicitly when you can't use `async with` (FastAPI startup hooks, long-lived service objects, etc.):

```python
patcher = PatcherClient(...)
try:
    titles = await patcher.fetch_patches()
finally:
    await patcher.aclose()
```

## Talking to the per-service clients directly

`PatcherClient` exposes three composed collaborators as attributes. Reach for them when the convenience methods above don't cover what you need:

::::{grid} 1 1 3 3
:gutter: 2
:padding: 0

:::{grid-item-card} {iconify}`material-icon-theme:cloud` `patcher.jamf`
:link: /reference/jamf_client
:link-type: doc

A {class}`~patcher.JamfClient` instance. Use directly for Jamf API calls that `fetch_patches` doesn't compose. For example, {meth}`~patcher.JamfClient.get_title_reports` for per-device detail.
:::

:::{grid-item-card} {iconify}`material-icon-theme:database` `patcher.api`
:link: /reference/patcher_api_client
:link-type: doc

A {class}`~patcher.PatcherAPIClient` instance (`None` when `enable_installomator=False`). Hit `/apps`, `/apps/{slug}`, `/apps/{slug}/sources`, or `/apps/{slug}/generate-label` for one-off catalog lookups outside the patch-matching flow.
:::

:::{grid-item-card} {iconify}`material-icon-theme:folder` `patcher.data`
:link: /reference/data_manager
:link-type: doc

The {class}`~patcher.core.data_manager.DataManager` instance. Holds the on-disk patch-data cache. Call `data.reset_cache()` to wipe it; `data.titles` is a get/set property for the most recent fetched list.
:::

::::

See the {doc}`/reference/index` for the full per-class method docs.
