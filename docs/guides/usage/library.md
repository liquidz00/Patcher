---
description: "Use Patcher as a Python library through PatcherClient: instantiate, fetch patch data from Jamf, analyze and filter, diff snapshots, detect drift, and export reports, all async and keyring-free."
---

(library-guides)=

# Library

:::{rst-class} lead
Everything `patcherctl` does, as importable async Python.
:::

---

Patcher is a library first and a CLI second. The same domain code that backs every `patcherctl` subcommand is reachable through one class, {class}`~patcher.core.patcher_client.PatcherClient`. Import it, hand it Jamf credentials, and call methods that fetch, analyze, and export patch data. Nothing the CLI does is off-limits to a script.

::::{highlights}
{iconify}`octicon:workflow-16` Inside a larger program
: Wiring Patcher into a Python automation (a scheduled job, a Slack bot, a custom dashboard) rather than shelling out to `patcherctl`.

{iconify}`octicon:code-16` Typed results
: You want typed return values ({class}`~patcher.core.models.patch.PatchTitle` objects) to filter and transform in code.

{iconify}`octicon:server-16` Explicit credentials
: Running on a host where you pass credentials directly (CI, a server) instead of through the interactive setup wizard.
::::

## Instantiation

Library callers pass Jamf credentials directly. An in-memory config is built internally, so no keyring backend is required and nothing is written to disk on construction. `PatcherClient` is an async context manager; use `async with` so the underlying Jamf and Patcher API connection pools are released cleanly.

```python
import asyncio
from patcher import PatcherClient

async def main():
    async with PatcherClient(
        client_id="...",
        client_secret="...",
        server="https://yourorg.jamfcloud.com",
    ) as patcher:
        ...  # work happens here; pools close on exit

asyncio.run(main())
```

If you have already run `patcherctl` setup on this Mac, skip the explicit credentials and read keychain-backed state instead with {meth}`PatcherClient.from_state() <patcher.core.patcher_client.PatcherClient.from_state>`. It pulls Jamf credentials from the keychain plus the UI customization and `enable_installomator` / `enable_homebrew` toggles from the property list. Any `__init__` keyword (commonly `concurrency` or `debug`) can be passed as an override.

```python
async with PatcherClient.from_state(concurrency=10) as patcher:
    ...
```

### Construction options

| Kwarg | Default | Purpose |
|---|---|---|
| `client_id`, `client_secret`, `server` | required | Jamf API credentials |
| `concurrency` | `5` | Max concurrent Jamf API requests |
| `enable_installomator` | `True` | Set to `False` to skip the catalog client entirely. `patcher.api` becomes `None` and `match_titles` is never called during `fetch_patches`. |
| `disable_cache` | `False` | Disable on-disk caching under `~/Library/Application Support/Patcher/`. Useful for stateless / CI runs. |

```python
async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
    concurrency=10,
    enable_installomator=False,
    disable_cache=True,
) as patcher:
    ...
```

## Export

{meth}`~patcher.core.patcher_client.PatcherClient.fetch_patches` is the one call that gathers what a report needs: it pulls policies and summaries from Jamf, then (by default) matches each title against the Installomator catalog to populate `install_label`. It returns a list of {class}`~patcher.core.models.patch.PatchTitle` objects. {meth}`~patcher.core.patcher_client.PatcherClient.export` then writes those titles to one or more report formats and returns a mapping of format to output path. With no `formats` argument it emits all four (`excel`, `html`, `pdf`, `json`).

```python
from pathlib import Path
from patcher import PatcherClient

async with PatcherClient.from_state() as patcher:
    titles = await patcher.fetch_patches(
        sort_by="Released",
        omit_recent_hours=48,
        include_ios=True,
    )
    await patcher.export(
        titles,
        output_dir=Path("~/reports").expanduser(),
        formats={"pdf", "json"},
        date_format="%B %Y",
    )
```

`fetch_patches` takes keyword arguments that mirror the CLI's flags, for example `include_ios=True` to append per-iOS-version summaries, `sort_by="released"` to order the result, and `omit_recent_hours=24` to drop titles released in the last day. Pass `match_installomator=False` to skip the catalog match entirely. {meth}`export <patcher.core.patcher_client.PatcherClient.export>` returns the dict of written-file paths, keyed by format.

### Customizing report appearance

PDF report styling (header text, footer text, custom font, logo, HTML header color) is configured via Patcher's property list. UI configuration only applies to PDF and HTML formats; Excel and JSON exports render correctly without it. See {ref}`property_list_file` for the full plist schema, valid keys, and how to modify them.

### iOS device data

Passing `include_ios=True` appends iOS / mobile device data to the report so you can see what's running on your fleet alongside the macOS patch coverage. Behind the scenes Patcher calls three Jamf APIs:

- {meth}`~patcher.clients.jamf.JamfClient.get_device_ids` pulls the IDs of all enrolled mobile devices.
- {meth}`~patcher.clients.jamf.JamfClient.get_device_os_versions` resolves each ID to its current OS version.
- {meth}`~patcher.clients.jamf.JamfClient.get_sofa_feed` fetches the latest released iOS/iPadOS versions from the [SOFA feed](https://sofa.macadmins.io/) to determine "on the latest" vs "behind."

### Homebrew Cask matching

Constructing the client with `enable_homebrew=True` widens catalog matching to a second dimension: the catalog's [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) source, which covers apps that carry no Installomator label and exposes identity fields (bundle ID, canonical name) that labels often omit. An Installomator hit lands in each title's `install_label`; a Homebrew Cask hit lands in the `homebrew_cask` field; an app covered by both gets both.

```python
from pathlib import Path
from patcher import PatcherClient

async with PatcherClient.from_state(enable_homebrew=True) as patcher:
    titles = await patcher.fetch_patches()
    # titles[n].homebrew_cask holds CaskMatch stubs for Cask-covered apps
    await patcher.export(titles, output_dir=Path("~/reports").expanduser())
```

### Disabling Installomator matching

Construct `PatcherClient` with `enable_installomator=False` to turn the catalog client off entirely. The plist value is ignored in favor of the explicit kwarg:

```python
patcher = PatcherClient(
    client_id=...,
    client_secret=...,
    server=...,
    enable_installomator=False,
)
```

With `enable_installomator=False`, `PatcherClient.api` is `None` and `match_titles` is never called from `fetch_patches`. The `install_label` field on every {class}`~patcher.core.models.patch.PatchTitle` stays empty.

## Analyze

{meth}`~patcher.core.patcher_client.PatcherClient.analyze` filters and sorts the titles you fetched against a named criterion, the same criteria the CLI exposes (for example `"most-installed"` or `"below-threshold"`). For type-checked, autocomplete-friendly access, construct {class}`~patcher.core.analyze.TitleFilter` directly instead of passing a string.

```python
from patcher import PatcherClient, TitleFilter

async with PatcherClient.from_state() as patcher:
    titles = await patcher.fetch_patches()

    # PatcherClient.analyze: kebab-case criterion string
    below = await patcher.analyze(titles, criteria="below-threshold", threshold=50.0)

    # Or call TitleFilter methods directly (same result, less indirection)
    least = TitleFilter(titles).least_installed(top_n=5)
    high_missing = TitleFilter(titles).high_missing(top_n=10)
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

{meth}`analyze <patcher.core.patcher_client.PatcherClient.analyze>` takes a kebab-case criterion string and returns the filtered list of {class}`~patcher.core.models.patch.PatchTitle` objects. {meth}`analyze_excel <patcher.core.patcher_client.PatcherClient.analyze_excel>` is the saved-report variant (Excel hydration is parked for v3.0.1; today it filters the cached titles regardless of the path passed). {meth}`analyze_trend <patcher.core.patcher_client.PatcherClient.analyze_trend>` operates across cached datasets over time.

For full method signatures see {class}`~patcher.core.analyze.TitleFilter` and {class}`~patcher.core.analyze.TrendAnalysis`.

### Criteria

Two criteria families drive analyze, used in different contexts:

- {class}`~patcher.core.analyze.TitleFilter` for analyzing a **single** patch report
- {class}`~patcher.core.analyze.TrendAnalysis` for analyzing patch data **over time**, comparing across multiple cached datasets

Filter criteria: `most-installed`, `least-installed`, `oldest-least-complete`, `below-threshold`, `recent-release`, `zero-completion`, `top-performers`, `high-missing`, `installomator`. Trend criteria (requiring at least two cached datasets): `patch-adoption`, `release-frequency`, `completion-trends`.

CLI criteria names are dash-flexible, but library method names use the underscore form (`TitleFilter(titles).most_installed()`).

### Generating a summary

Pass `save_to=...` to `analyze_trend` to write an HTML version of the analysis alongside the returned DataFrame.

```python
async with PatcherClient.from_state() as patcher:
    trend = await patcher.analyze_trend(
        "patch-adoption",
        save_to="~/Reports/trend-adoption.html",
    )
```

The DataFrame is returned regardless of whether `save_to` is provided. If the DataFrame is empty (e.g. no cached data matches the criterion), no file is written.

## Diff

{meth}`~patcher.core.patcher_client.PatcherClient.diff` compares two patch-state snapshots. It reuses the same `~/Library/Caches/Patcher/patch_data_*.pkl` snapshots that drive analyze, so it works against history Patcher has already been collecting.

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

### What gets compared

A title is **changed** if any of these differ between the two snapshots: completion percent, hosts patched, total hosts, or latest version. Released date and Installomator label changes are intentionally ignored (they tend to flip for upstream reasons unrelated to fleet state). A {class}`~patcher.core.analyze.TitleChange` row carries both before/after values plus the deltas, so consumers don't need to recompute.

The flag arguments (`since`, `all_time`, `between`, `no_fetch`) select which two snapshots get compared; see [the CLI's snapshot-selection table](cli.md#diff) for the full matrix.

## Drift

{meth}`~patcher.core.patcher_client.PatcherClient.detect_drift` reports where upstream catalog sources disagree on the current version. It works even when `enable_installomator=False`; it constructs the catalog client on demand. The catalog endpoints are public, so no credentials are required.

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

### What gets returned

Every catalog source independently reports a current version for each app (Installomator's `appNewVersion`, Homebrew Cask's `version`). When they disagree, one source is probably silently stuck. A {class}`~patcher.clients.patcher_api.DriftEntry` carries the slug, name, vendor, every source's reported version, and a `leader`/`laggard` pair (the highest and lowest parsed versions). Both are `None` when any version couldn't be parsed; the raw versions are still in `versions` so you can render the disagreement without ordering it.

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

## Reset

{meth}`PatcherClient.reset <patcher.core.patcher_client.PatcherClient.reset>` mirrors the CLI's four reset kinds (`cache`, `UI`, `creds`, `full`). The library version doesn't re-launch the setup wizard after a `"full"` reset; re-construct a `PatcherClient` yourself once you've populated new credentials.

```python
async with PatcherClient.from_state() as patcher:
    await patcher.reset("cache")
    await patcher.reset("UI")
    await patcher.reset("creds")
    await patcher.reset("creds", credential="url")
    await patcher.reset("full")
```

The `"creds"`, `"UI"`, and `"full"` kinds require keychain-backed credentials and raise {class}`~patcher.core.exceptions.PatcherError` when called on a client constructed with in-memory credentials.

:::{seealso}
For more about cached data and where Patcher stores it, see {doc}`/project/data-storage`.
:::

## End to end

Putting the pieces together: fetch, filter to the titles that are behind, and export just those to a PDF.

```{code-block} python
import asyncio
from patcher import PatcherClient

async def main():
    async with PatcherClient(
        client_id="...",
        client_secret="...",
        server="https://yourorg.jamfcloud.com",
    ) as patcher:
        titles = await patcher.fetch_patches(sort_by="completion_percent")
        behind = await patcher.analyze(titles, "below-threshold", threshold=70.0)
        paths = await patcher.export(
            behind,
            output_dir="./reports",
            formats={"pdf"},
            report_title="Behind on Patching",
        )
        print(f"Wrote {paths['pdf']}")

asyncio.run(main())
```

## Working with individual clients

If you only need a subset (Jamf without Installomator, or Installomator labels without Jamf credentials), instantiate the per-service clients directly.

### `JamfClient` standalone

```python
from patcher import JamfClient

client = JamfClient.from_credentials(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
)
try:
    ids = await client.get_device_ids()
    versions = await client.get_device_os_versions(ids)
finally:
    await client.aclose()
```

{meth}`JamfClient.from_credentials <patcher.clients.jamf.JamfClient.from_credentials>` wraps credentials in an in-memory {class}`~patcher.core.config_manager.ConfigManager`. No keyring backend, no disk I/O.

### `InstallomatorClient` standalone

Fetch and parse Installomator labels without any Jamf credentials:

```python
from patcher import InstallomatorClient

iom = InstallomatorClient()
labels = await iom.get_labels()
firefox = await iom.get_label("firefox")
print(firefox.expected_team_id, firefox.download_url)
```

The client covers label discovery (`list_available_labels`), single-label fetch (`get_label`), and bulk fetch (`get_labels`). Matching Jamf patch titles against the Installomator catalog is a separate module-level function, {func}`patcher.core.matching.match_titles`, which `PatcherClient.fetch_patches` runs automatically against the public Patcher API catalog rather than fetching `Labels.txt` directly.
