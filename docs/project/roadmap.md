---
description: "Features and source integrations planned for upcoming Patcher releases. Homebrew Cask, AutoPkg, Jamf App Installers, and CVE sourcing for apps."
---

# Roadmap

:::{rst-class} lead
Features and source integrations planned for upcoming Patcher releases.
:::

This page is the source of truth for work that is scoped but not yet shipped. Items here are tracked in the [Patcher repository](https://github.com/liquidz00/Patcher); the API surface for some of them is already partially in place (the `App` model in the catalog reserves fields like `cves` that no ingest currently populates).

**Status legend:** {iconify}`lucide:circle-dot style=color:#ea580c` In progress &nbsp;&nbsp; {iconify}`lucide:circle style=color:#9ca3af` Planned &nbsp;&nbsp; {iconify}`lucide:circle-check style=color:#16a34a` Shipped

::::{grid} 1 1 2 2
:gutter: 2
:padding: 0

:::{grid-item-card} {iconify}`simple-icons:homebrew` Homebrew Cask {iconify}`lucide:circle-dot style=color:#ea580c`
:link: roadmap-homebrew-cask
:link-type: ref

Pull Cask metadata (bundle ID, canonical name, vendor) as a second matching dimension alongside Installomator.
:::

:::{grid-item-card} {iconify}`lucide:workflow` AutoPkg {iconify}`lucide:circle style=color:#9ca3af`
:link: roadmap-autopkg
:link-type: ref

Match Jamf titles against the AutoPkg recipe catalog for broader, multi-maintainer coverage.
:::

:::{grid-item-card} {iconify}`lucide:store` Jamf App Installers {iconify}`lucide:circle style=color:#9ca3af`
:link: roadmap-jai
:link-type: ref

Flag titles already covered by JAI so reports can surface "Patcher may not need to track this."
:::

:::{grid-item-card} {iconify}`lucide:shield-alert` CVE sourcing for apps {iconify}`lucide:circle style=color:#9ca3af`
:link: roadmap-cves
:link-type: ref

Attach known CVE identifiers to catalog records so reports highlight titles with public vulnerabilities.
:::

::::

(roadmap-homebrew-cask)=

## Homebrew Cask

Pull metadata from the [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) catalog as a second matching dimension alongside Installomator. Cask carries fields Installomator labels often omit (bundle ID, canonical app name, vendor) and covers apps with no Installomator label at all.

**Planned scope**

- Per-Cask token ingestion (`api/patcher_api/ingest/homebrew.py` already exists in skeleton form).
- Stitch logic that joins Cask records into the `apps` catalog when bundle IDs or normalized slugs match an existing record.
- A toggle on the `patcherctl` matching pipeline so callers can opt in or out of Cask-sourced matches.

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

(roadmap-cves)=

## CVE sourcing for apps

Attach known CVE identifiers to catalog records so reports can highlight titles with public vulnerabilities. The `App` schema already reserves a `cves: list[str]` field; the work is to pick a source and populate it.

**Candidate sources**

- [NVD](https://nvd.nist.gov/) (NIST's National Vulnerability Database) for canonical CVE entries with severity and affected version ranges.
- [OSV.dev](https://osv.dev/) for a unified open-source vulnerability feed.
- [GitHub Advisory Database](https://github.com/advisories) for advisories scoped to packages and their ecosystems.

**Planned scope**

- Ingest path that joins CVE IDs to catalog records by vendor + product name (with fallback to bundle ID where available).
- Severity and "affected versions" surfaced on `/apps/{slug}` so a single catalog read is enough for a security-aware report.
- A `--with-cves` flag on `patcherctl export` that adds a vulnerability column to the report.
