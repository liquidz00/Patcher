---
description: "Features and source integrations planned for upcoming Patcher releases. Homebrew Cask, AutoPkg, and Jamf App Installers."
---

# Roadmap

:::{rst-class} lead
Features and source integrations planned for upcoming Patcher releases.
:::

---

This page is the source of truth for work that is scoped but not yet shipped. Items here are tracked in the [Patcher repository](https://github.com/liquidz00/Patcher).

**Status legend:** {iconify}`lucide:circle-dot style=color:#ea580c` In progress &nbsp;&nbsp; {iconify}`lucide:circle style=color:#9ca3af` Planned &nbsp;&nbsp; {iconify}`lucide:circle-check style=color:#16a34a` Shipped

::::{grid} 1 1 2 2
:gutter: 2
:padding: 0

:::{grid-item-card} {iconify}`simple-icons:homebrew` Homebrew Cask {iconify}`lucide:circle-check style=color:#16a34a`
:link: roadmap-homebrew-cask
:link-type: ref

Cask metadata (bundle ID, canonical name, vendor) joined into the catalog and matchable as a second dimension alongside Installomator.
:::

:::{grid-item-card} {iconify}`lucide:workflow` AutoPkg {iconify}`lucide:circle-check style=color:#16a34a`
:link: roadmap-autopkg
:link-type: ref

Match Jamf titles against the AutoPkg recipe catalog for broader, multi-maintainer coverage.
:::

:::{grid-item-card} {iconify}`lucide:store` Jamf App Installers {iconify}`lucide:circle-check style=color:#16a34a`
:link: roadmap-jai
:link-type: ref

Flag titles already covered by JAI so reports can surface "Patcher may not need to track this."
:::

::::

(roadmap-homebrew-cask)=

## Homebrew Cask

Metadata from the [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) catalog is now a second matching dimension alongside Installomator. Cask carries fields Installomator labels often omit (bundle ID, canonical app name, vendor) and covers apps with no Installomator label at all.

**Shipped**

- Per-Cask token ingestion (`api/patcher_api/ingest/homebrew.py`) into the `homebrew_casks` table.
- Stitch logic that joins Cask records into the `apps` catalog (by token and by artifact `.app` name) and creates Cask-only rows for apps no Installomator label covers.
- An opt-in toggle on the `patcherctl` matching pipeline: `patcherctl export --homebrew` (and `PatcherClient(enable_homebrew=True)`) populates `PatchTitle.homebrew_cask` and adds a `Homebrew` coverage column to reports. See {ref}`Homebrew matching <homebrew>`.

(roadmap-autopkg)=

## AutoPkg

Match Jamf titles against the [AutoPkg](https://github.com/autopkg/autopkg) recipe catalog. AutoPkg's recipe index is large and multi-maintainer, so coverage often outruns Installomator for niche apps.

**Planned scope**

- Recipe-index ingestion across the major maintainer repos.
- Per-app recipe enumeration (download, pkg, munki, jamf, intune variants) surfaced via the existing `/apps/{slug}/sources` endpoint.
- Resolution of `parent_identifier` chains so the catalog records the canonical download recipe per app.

(roadmap-jai)=

## Jamf App Installers

Flag titles that already have coverage in the [Jamf App Installers](https://learn.jamf.com/r/en-US/jamf-pro-documentation-current/App_Installers) catalog. The intent is not to replace JAI; it is to surface "this title is covered by JAI; you may not need Patcher to track its patch state" as a signal in reports.

**Planned scope**

- Periodic ingest of the public JAI catalog.
- Per-title indicator in exported PDF/HTML/Excel reports.
- Optional filter on `patcherctl analyze` to focus on titles JAI does not cover.
