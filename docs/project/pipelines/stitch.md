---
description: "How Patcher merges Installomator, Homebrew Cask, AutoPkg, Mac App Store, and Jamf App Installers data into a single canonical catalog of macOS apps."
---

(stitching)=

# Stitching

:::{rst-class} lead
How heterogeneous upstream sources become one canonical app record.
:::

---

The Patcher catalog has one row per macOS app, with normalized fields the API serves: `slug`, `name`, `vendor`, `current_version`, `download_url`, `install_method`, and so on. But none of the upstream sources Patcher tracks (Installomator, Homebrew Cask, AutoPkg, Mac App Store, Jamf App Installers) produces data in that shape. Each ships its own format optimized for its own tooling.

The stitch pipeline is what reconciles them. This page is the mental model. For the source-level reference, see {doc}`/reference/api/source/stitch`.

## The two-layer storage shape

Upstream data and canonical data live in two separate tables, on purpose:

- **`app_source_details`** holds one row per app per source, with the source's *native* payload in a JSON column (so an Installomator label looks exactly like an Installomator label, a Cask entry looks exactly like a Cask entry, etc.). One table can hold a `firefox` Installomator label, a `firefox` Cask entry, and an AutoPkg `Firefox.download.recipe` side by side.
- **`apps`** holds one row per app with the *normalized* fields. This is what `GET /apps*` serves. Every column here is derived from the source details by the stitch pipeline.

Keeping the layers separate means the API can answer two different kinds of questions: "what does Patcher think the canonical version is?" (canonical row) and "what does each upstream source say?" (source-detail rows). And it means adding a new upstream source is an additive change. You write an ingest module that fills its own JSON column without touching how existing sources are stored.

```{mermaid}
flowchart LR
    INST[Installomator labels] --> SD[(app_source_details)]
    CASK[Homebrew Cask] --> SD
    AP[AutoPkg recipes] --> SD
    MAS[Mac App Store] --> SD
    JAI[Jamf App Installers] --> SD
    SD --> STITCH[stitch pipeline]
    STITCH --> APPS[(apps)]
    APPS --> API[GET /apps*]
```

## What stitching actually does

For every app the ingest pipeline has touched, stitch walks the source-detail rows and projects them into a canonical app record. For each field on the canonical row, the rules are:

1. **Match source rows to a canonical app.** Apps in different sources rarely share a perfect identifier. Stitch matches primarily on bundle ID where available (the most reliable signal), then falls back to normalized name comparison. The bundle-ID-first pass is what we call the *precision overlay*: when a source provides a high-confidence identifier, that wins; otherwise the name-based workhorse takes over.
2. **Pick the best available value for each field.** Stitch has a per-field fallback chain. For example, `current_version` checks Installomator's resolved `appNewVersion` first, then Cask's `version` field, then JAI's reported version. `download_url` does similar across the sources that publish one. The chain is biased toward the source most likely to have the freshest, cleanest value for that field.
3. **Record the source breakdown.** The canonical row's `sources` column lists every source that contributed to it. This is what powers `GET /apps?source=installomator` and the per-source coverage breakdown on the MCP `get_catalog_summary` tool.
4. **Warn about gaps.** Some fields can't be sourced from every upstream. Cask-only apps don't have an `expectedTeamID` (only Installomator carries that), so the label-generation endpoint emits a warning when a caller asks for a label built from a Cask-only app. Drift detection, similarly, only runs against apps where at least two sources publish a comparable version string.

## Why stitch isn't just a SQL JOIN

You could imagine a world where the canonical fields are computed inline at request time by joining `apps` and `app_source_details`. Patcher doesn't do that, for three reasons:

- **The fallback chains involve text normalization, version parsing, and source-priority logic.** Expressing that in SQL would be painful, and it would run on every request.
- **The catalog needs a stable hash to power ETag caching.** The hash is the SHA-256 of the SQLite file. If reads computed canonical fields on the fly, the file's bytes would be stable but the served bytes wouldn't reflect that, and ETag invalidation would be subtle.
- **Drift detection needs both views.** It compares the source-detail versions to spot disagreement, but writes its results against the canonical `apps` row. Two-table storage makes both halves trivial.

So stitch runs as part of the catalog-refresh schedule. It reads the source-detail rows, computes canonical fields in Python, and writes them back to `apps`. The API then serves `apps` directly with no per-request projection cost.

## What changes when an upstream source moves

When an upstream source publishes a new version of an app:

1. The relevant ingest module picks up the new data on the next refresh and updates the `app_source_details` row for that source.
2. Stitch runs (immediately for admin upserts, on the daily refresh otherwise) and re-projects the canonical row using the updated source data.
3. The catalog file's bytes change, so its SHA-256 changes, so the ETag changes, so clients revalidate and see the new data.

End-to-end latency depends on the source: Cask refreshes the same day it merges upstream; AutoPkg recipes follow their own cadence; Installomator's resolved values may need the {doc}`macOS runner pass <resolution>` for dynamic fields. The stitch step itself is fast (it's a Python loop over rows already in memory).

## Adding a new source

The pattern, if anyone ever wires up a new upstream:

1. Add a new JSON column to `app_source_details` for the source's native payload.
2. Write an ingest module under `patcher_api/ingest/` that pulls from the upstream and populates that column for affected apps.
3. Update the stitch logic to read the new column in its per-field fallback chains (or to record it in the `sources` provenance list if it's coverage-only, like Jamf App Installers).
4. Add the source to the per-source coverage count in `get_catalog_summary`.

That's the extent of the change. The HTTP routes, the API client, the MCP tools all keep working unchanged because the canonical projection is the only thing they see.
