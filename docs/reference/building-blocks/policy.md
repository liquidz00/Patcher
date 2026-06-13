---
description: "Reference for patcher.policy: the catalog filter/seed constants and the per-format field policy that decides which columns reach an export."
---

# Policy

`patcher.policy` holds the catalog rules that are deliberately hardcoded rather than user-configurable. Each constant is owned by a different layer (ingest, matching, stitch, export) and is independent of the others. They live in one module so the decisions are reviewable in a single place instead of being scattered next to the code that happens to read them.

## Catalog constants

`INGEST_EXCLUDED_TEAM_IDS`
: Apple Developer Team IDs dropped while parsing Installomator fragments. These are labels with broken or non-standard data (for example, `lcadvancedvpnclient`, and the `zulujdk*` labels whose versioning relies on HTML scraping). Excluding them at ingest keeps the bad records out of the catalog entirely.

`IGNORED_TITLES`
: The client matcher's skip list of Jamf patch-title names, written as glob patterns (`Adobe *`, `Jamf *`, `Apple macOS *`, ...). A title here is never matched against the catalog, either because it is managed out-of-band (Adobe via the Admin Console), updated by its own mechanism (Jamf, Apple), or no longer supported. This is distinct from the user-configurable `ignored_titles` plist setting, which is a per-install preference layered on top.

`CURATED_BUNDLE_IDS`
: A slug → bundle_id seed used during the catalog stitch. Some install sources carry no bundle identifier, so Jamf App Installers titles cannot attach to them automatically. Each entry supplies the authoritative `bundleId` (taken from the App Installers titles API) so the stitch can bridge the gap for high-value apps like Zoom, Docker, and OBS.

`IGNORED_EXPORT_COLUMNS`
: The internal columns dropped from the rendered reports. See [the field policy below](#export-field-policy).

(export-field-policy)=
## Export field policy

A `PatchTitle` carries a few fields that exist purely as internal plumbing: `title_id` and `name_id` are Jamf join keys, and `install_label` / `homebrew_cask` are raw matcher output. Whether those reach an export depends on the format, because the formats serve two different audiences.

**Rendered reports (PDF, Excel, HTML)** are for a human reading a patch report. {class}`~patcher.core.exporter.Exporter` drops `IGNORED_EXPORT_COLUMNS` from the DataFrame before rendering, so the join keys and raw matcher fields never show up as columns. (The Homebrew column is the exception: the raw `homebrew_cask` field is dropped, then a readable `Homebrew` column is derived from it only when a cask actually matched.)

**JSON** is a machine-to-machine transport. It is serialized straight from the models via {func}`~patcher.core.serialization.titles_to_dict` with no DataFrame round-trip, so it keeps every field, `title_id` and `name_id` included. A downstream consumer building a dashboard or alerting pipeline needs those identifiers to join back against Jamf.

```{note}
There is no toggle today: JSON always keeps the internal keys and the rendered formats always drop them. A future option could let JSON callers opt into the human-facing shape (dropping the internal keys) when they only want the report-visible fields.
```
