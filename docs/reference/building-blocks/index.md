---
layout: focused
description: "Stable reference for the layers under the entry-point clients: analyze, HTTP transport, config and data managers, PDF report writer, token manager, plist manager."
---

# Building Blocks

:::{rst-class} lead
Stable surface for extending Patcher. HTTP transport, analysis transforms, configuration and data persistence, PDF rendering.
:::

---

::::{grid} 1 2 3 3
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Analyze`
:link: analyze
:link-type: doc

Compose filters and trend criteria over a list of `PatchTitle` objects. The transform layer behind `patcherctl analyze`; reach for it when you want to slice patch data your own way.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `ConfigManager`
:link: config_manager
:link-type: doc

Owns Jamf credentials. Keychain-backed by default; pass `in_memory_credentials` for CI or non-macOS environments where the keychain isn't writable.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `DataManager`
:link: data_manager
:link-type: doc

Patch report persistence. Reads and writes the Parquet cache under `~/Library/Caches/Patcher/` that powers analyze and trend comparisons across snapshots.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Exporter`
:link: exporter
:link-type: doc

Renders patch titles to PDF, Excel, HTML, and JSON. A pure consumer: `DataManager` builds and caches the canonical frame, the exporter only writes the report files.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `HttpClient`
:link: http_client
:link-type: doc

Async `httpx` base every outbound client inherits from. Provides the per-instance semaphore and the `httpx.RequestError → APIResponseError` translation subclasses route through.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `PdfReport`
:link: pdf_report
:link-type: doc

`fpdf2`-backed renderer for branded patch reports. Handles font loading, logo placement, and per-page header/footer styling driven by the `ui_config` dict.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Policy`
:link: policy
:link-type: doc

The hardcoded catalog rules: which Installomator team IDs and Jamf titles are skipped, which bundle_ids are seeded for the stitch, and which internal columns are stripped from rendered reports.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Serialization`
:link: serialization
:link-type: doc

The shared conversions between `PatchTitle` objects and their DataFrame and dict forms. One place owns `model_dump`, so the cache, the diff path, and JSON export stay consistent.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `TokenManager`
:link: token_manager
:link-type: doc

OAuth token lifecycle for the Jamf Pro API. Acquires, caches, and refreshes bearer tokens; `JamfClient` drives it for you in normal use.
:::
::::

```{toctree}
:hidden:

analyze
config_manager
data_manager
exporter
http_client
pdf_report
policy
serialization
token_manager
```
