---
description: "How Patcher merges Installomator, Homebrew Cask, AutoPkg, and Jamf App Installers data into a single canonical catalog of macOS apps."
---

(stitching)=

# Stitching

:::{rst-class} lead
How diverse upstream sources become a single app record.
:::

---

The Patcher catalog has one row per macOS app, with the normalized fields the API serves: `slug`, `name`, `vendor`, `current_version`, `download_url`, `install_method`, and so on. Each upstream source ships its data in its own format, though. The stitch pipeline is what reconciles them into that single row. This page walks through how.

:::{definition} canonical record
The single, normalized row Patcher serves for an app, built by merging every source's data. One per app, in the `apps` table, and what every `GET /apps*` response returns.
:::

## The Two-Layer Storage Shape

Upstream data and canonical data live in the following two tables, separated intentionally:

::::{steps}

:::{step} `app_source_details`
Holds one row per app per source, with the source's *native* payload in a JSON column (so an Installomator label looks exactly like an Installomator label, a Cask entry looks exactly like a Cask entry, etc.). One table can hold an Installomator label, a Cask entry, and an AutoPkg recipe side by side.
:::

:::{step} `apps`
Holds one row per app with the *normalized* fields. This is what `GET /apps*` serves. Every column here is derived from the source details by the stitch pipeline.
:::
::::

Keeping the layers separate means the API can differentiate between the source of truth (canonical row) and the upstream source (source-detail rows). Adding new upstream sources can be done by writing an ingest module that fills its own JSON column without touching how existing sources are stored.

```{mermaid}
flowchart LR
    INST[Installomator labels] --> SD[(app_source_details)]
    CASK[Homebrew Cask] --> SD
    AP[AutoPkg recipes] --> SD
    JAI[Jamf App Installers] --> SD
    SD --> STITCH[stitch pipeline]
    STITCH --> APPS[(apps)]
    APPS --> API[GET /apps*]
```

## What Stitching Actually Does

For every app the ingest pipeline has touched, stitch walks the source-detail rows and projects them into a canonical app record. For each field on the canonical row, the rules are:

::::{steps}

:::{step} Match source rows to a canonical app.

Apps in different sources rarely share a perfect identifier. Stitch matches primarily on bundle ID where available, since it's the most reliable signal. When a source doesn't carry one, it falls back to comparing normalized names.
:::

:::{step} Pick the best available value for each field.

Stitch has a per-field fallback chain. For example, `current_version` checks Installomator's resolved `appNewVersion` first, then Cask's `version` field, then JAI's reported version. `download_url` does similar across the sources that publish one. The chain is biased toward the source most likely to have the freshest, cleanest value for that field.
:::

:::{step} Record the source breakdown.

The canonical row's `sources` column lists every source that contributed to it. This is what powers `GET /apps?source=installomator` and the per-source coverage breakdown on the MCP `get_catalog_summary` tool.
:::

:::{step} Warn about gaps.

Some fields can't be sourced from every upstream. Cask-only apps don't have an `expectedTeamID` (only Installomator carries that), so the label-generation endpoint emits a warning when a caller asks for a label built from a Cask-only app. Drift detection, similarly, only runs against apps where at least two sources publish a comparable version string.
:::
::::

## Why Stitch Isn't Just a SQL JOIN

Joining `apps` and `app_source_details` at request time is intentionally avoided for three primary reasons:

::::{markers}
:icon: octicon:database-16

:::{marker} The fallback chains involve real logic
Text normalization, version parsing, and source-priority. Expressing that in SQL would be painful, and it would run on every request.
:::

:::{marker} The cache key must match what's served
The `/apps*` ETag is a version token derived from the newest row timestamp. If reads computed canonical fields on the fly, the served bytes could change without any row (or token) moving, making ETag invalidation subtle. Precomputing keeps served bytes a pure function of stored rows.
:::

:::{marker} Drift detection needs both views
It compares the source-detail versions to spot disagreement, but writes its results against the canonical `apps` row. Two-table storage makes both halves trivial.
:::
::::

So stitch runs as part of the catalog-refresh schedule. It reads the source-detail rows, computes canonical fields in Python, and writes them back to `apps`. The API then serves `apps` directly with no per-request projection cost.

## What Changes When an Upstream Source Moves

When an upstream source publishes a new version of an app:

::::{steps}

:::{step} Ingest picks up the new data.

The relevant ingest module picks up the new data on the next refresh and updates the `app_source_details` row for that source.
:::

:::{step} Stitch re-projects the canonical row.

Stitch runs (immediately for admin upserts, on the daily refresh otherwise) and re-projects the canonical row using the updated source data.
:::

:::{step} The ETag changes.

The newest row timestamp advances, so the catalog version token changes, so the ETag changes, so clients revalidate and see the new data.
:::

::::

How long this takes from end to end depends on the source. Cask refreshes the same day it merges upstream. AutoPkg recipes follow their own cadence. Installomator's resolved values may need the {doc}`macOS runner pass <resolution>` for dynamic fields. The stitch step itself is fast (it's a Python loop over rows already in memory).

## Adding a New Source

The pattern, if anyone ever wires up a new upstream:

::::{steps}

:::{step} Add a new JSON column.

Add a new JSON column to `app_source_details` for the source's native payload.
:::

:::{step} Write an ingest module.

Write an ingest module under `patcher_api/ingest/` that pulls from the upstream and populates that column for affected apps.
:::

:::{step} Update the stitch logic.

Update the stitch logic to read the new column in its per-field fallback chains (or to record it in the `sources` provenance list if it's coverage-only, like Jamf App Installers).
:::

:::{step} Add the coverage count.

Add the source to the per-source coverage count in `get_catalog_summary`.
:::

::::

That's the extent of the change. The HTTP routes, the API client, the MCP tools all keep working unchanged because the canonical projection is the only thing they see.

```{seealso}
For the source-level reference, see {doc}`/reference/api/source/stitch`.
```
