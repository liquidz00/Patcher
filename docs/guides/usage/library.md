---
description: "Use Patcher as a Python library through PatcherClient: instantiate, fetch patch data from Jamf, analyze and filter, diff snapshots, detect drift, and export reports, all async and keyring-free."
---

(library-guides)=

# Library

:::{rst-class} lead
Everything `patcherctl` does, as importable async Python.
:::

---

The same domain code that backs every `patcherctl` subcommand is reachable through one class, {class}`~patcher.core.patcher_client.PatcherClient`. Import it, hand it Jamf credentials, and call methods that fetch, analyze, and export patch data. Nothing the CLI does is off-limits to a script.

::::{highlights}
{iconify}`octicon:workflow-16` Inside a larger program
: Wiring Patcher into a Python automation rather than shelling out to `patcherctl`.

{iconify}`octicon:code-16` Typed results
: You want typed return values to filter and transform in code.

{iconify}`octicon:server-16` Explicit credentials
: Running on a host where you pass credentials directly instead of the setup wizard.
::::

## Instantiation

Library callers can pass Jamf credentials directly when constructing {class}`~patcher.core.patcher_client.PatcherClient` objects. These clients are async context managers, so to release the underlying API connections cleanly, be sure to use `async with`.

```{code-block} python
:caption: Creating a `PatcherClient` instance in async context

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

### Construction Options

`client_id`, `client_secret`, `server` *(required)*
: Jamf API credentials

`concurrency`
: Max concurrent Jamf API requests *(Default: 5)*

`enable_installomator`
: Set to `False` to skip the catalog client entirely. *(Default: True)*

`disable_cache`
: Disable on-disk caching. Useful for stateless / CI runs *(Default: False)*

```{code-block} python
:caption: Any `__init__` keyword can be passed as an override

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

The {meth}`~patcher.core.patcher_client.PatcherClient.fetch_patches` method is the one call that gathers everything a report needs. It pulls policies and summaries from Jamf and returns a list of {class}`~patcher.core.models.patch.PatchTitle` objects. The {meth}`~patcher.core.patcher_client.PatcherClient.export` method then writes those titles to one or more formats and returns a mapping of format-to-output-path. To export all four formats (Excel, PDF, JSON, HTML), omit the `formats` argument entirely.

```{code-block} python
:caption: Gather titles and export

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

:::{card}
:class-card: sd-card
Keyword arguments mirror the CLI's flags.
^^^

`include_ios=True`
: Append per-iOS-version summaries

`sort_by="released"`
: Order the result

`omit_recent_hours=24`
: Drop titles released in the last day

`match_installomator=False`
: Skip catalog match entirely
:::

### Customizing Report Appearance

PDF report styling (header text, footer text, custom font, logo, HTML header color) is configured via Patcher's property list. UI configuration only applies to PDF and HTML formats; Excel and JSON exports render correctly without it. See {ref}`Patcher's property list file <property_list_file>` for the full plist schema and valid keys.

### iOS Device Data

Passing `include_ios=True` appends iOS / mobile device data to the report so you can see what's running on your fleet alongside the macOS patch coverage. Behind the scenes Patcher calls three Jamf APIs:

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

### Homebrew Cask Matching

Constructing the client with `enable_homebrew=True` widens catalog matching to [Homebrew Cask's](https://github.com/Homebrew/homebrew-cask) catalog, which covers apps that carry no Installomator label. Installomator matches are assigned to each title's `install_label` attribute, Cask matches are assigned to each title's `homebrew_cask` attribute.

```python
from pathlib import Path
from patcher import PatcherClient

async with PatcherClient.from_state(enable_homebrew=True) as patcher:
    titles = await patcher.fetch_patches()
    # titles[n].homebrew_cask holds CaskMatch stubs for Cask-covered apps
    await patcher.export(titles, output_dir=Path("~/reports").expanduser())
```

### Disabling Installomator Matching

```{note}
Explicit keyword arguments take precedence over property list values.
```

```{code-block} python
:caption: Construct `PatcherClient` with `enable_installomator=False` to turn the catalog client off entirely.

patcher = PatcherClient(
    client_id=...,
    client_secret=...,
    server=...,
    enable_installomator=False,
)
```

With matching disabled, patch title fetching never calls the matching algorithm. `install_label` field on every patch title stays empty.

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

    # Filter a saved Excel report directly (skip fetching patches)
    stale = await patcher.analyze_excel(
        "/path/to/report.xlsx",
        criteria="most-installed",
    )
```

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

:::{admonition} Important
:class: warning

Panda's [Dataframes](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html) are returned when perform trend analysis.

```python
async with PatcherClient.from_state() as patcher:
    trend = await patcher.analyze_trend("patch-adoption")
    print(trend.head())
```
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

CLI criteria names are dash-flexible, but library method names use the underscore form (`TitleFilter(titles).most_installed()`).

```{seealso}
For full method signatures see {class}`~patcher.core.analyze.TitleFilter` and {class}`~patcher.core.analyze.TrendAnalysis`.
```

### Generating a Summary

To write an HTML version of the analysis alongside the returned DataFrame, pass `save_to=...` when analyzing trends.

```{code-block} python
:caption: Creating HTML summary from trend analysis

async with PatcherClient.from_state() as patcher:
    trend = await patcher.analyze_trend(
        "patch-adoption",
        save_to="~/Reports/trend-adoption.html",
    )
```

The DataFrame is returned regardless of whether a summary is generated or not. No file is written if the DataFrame is empty (e.g. no cached data matches the criterion).

## Diff

Compare two patch-state snapshots against each other to determine differences between them. This method reuses the same cache snapshots, so it works against history Patcher has already been collecting.

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

:::{tip}
To compare two snapshots, construct a {class}`~patcher.core.analyze.Diff` directly. Each side can be a `PatchTitle` list, a DataFrame, or a path to a `.pkl`/`.xlsx` export, as long as it's a Patcher-produced report. See {class}`~patcher.core.analyze.Diff` for full source reference.
:::

### What Gets Compared

A title is **changed** if completion percent, hosts patched, total hosts, or latest version differ between the two snapshots. Released date and Installomator label changes are intentionally ignored. A {class}`~patcher.core.analyze.TitleChange` row carries both before/after values plus the deltas, so consumers don't need to recompute.

The flag arguments (`since`, `all_time`, `between`, `no_fetch`) select which two snapshots get compared. See [the CLI's snapshot-selection table](cli.md#diff) for the full matrix.

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

### What Gets Returned

Every catalog source independently reports a current version for each app (Installomator's `appNewVersion`, Homebrew Cask's `version`). When they disagree, one source is probably silently stuck. A {class}`~patcher.clients.patcher_api.DriftEntry` carries the slug, name, vendor, every source's reported version, and a `leader`/`laggard` pair (the highest and lowest parsed versions). Both are `None` when any version couldn't be parsed, the raw versions are still in `versions` so you can render the disagreement without ordering it.

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

The {meth}`~patcher.core.patcher_client.PatcherClient.reset` method mirrors the CLI's four reset kinds, but only `cache` is broadly useful for library usage. It empties the on-disk patch cache and works in any credential mode.

```python
async with PatcherClient.from_state() as patcher:
    await patcher.reset("cache")
```

The other three (`UI`, `creds`, `full`) clear keychain and property-list state, so they require keychain-backed credentials and raise {class}`~patcher.core.exceptions.PatcherError` on a client built with in-memory credentials. Reach for those from the {doc}`CLI </guides/usage/cli>`.

## End to End

Putting the pieces together: fetch, filter to the titles that are behind, and export just those to a PDF.

```{code-block} python
:caption: Full end to end example

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

## Working with Individual Clients

If you only need a subset (Jamf without Installomator, or Installomator labels without Jamf credentials), instantiate the per-service clients directly.

### `JamfClient` Standalone

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

### `InstallomatorClient` Standalone

Fetch and parse Installomator labels without any Jamf credentials:

```python
from patcher import InstallomatorClient

iom = InstallomatorClient()
labels = await iom.get_labels()
firefox = await iom.get_label("firefox")
print(firefox.expected_team_id, firefox.download_url)
```

The client covers label discovery (`list_available_labels`), single-label fetch (`get_label`), and bulk fetch (`get_labels`). Matching Jamf patch titles against the Installomator catalog is a separate module-level function, {func}`patcher.core.matching.match_titles`, which `PatcherClient.fetch_patches` runs automatically against the public Patcher API catalog rather than fetching `Labels.txt` directly.
