---
description: "The four upstream sources Patcher stitches into its catalog: Installomator, Homebrew Cask, AutoPkg, and Jamf App Installers. What each contributes and where its coverage ends."
---

(catalog-sources)=

# Catalog Sources

:::{rst-class} lead
Upstream sources that feed the stitched catalog, and what each one is good for.
:::

---

The Patcher catalog is not a single dataset. It is stitched together from several independent upstream sources, each with its own release schedule, data format, and coverage gaps. A canonical app record on `api.patcherctl.dev` is the merge of whatever those sources happened to know about that app. This page describes each source on its own terms. For *how* the merge happens (per-field fallback chains, conflict resolution, drift detection), see {doc}`/project/architecture/resolution` and {doc}`/project/architecture/stitch`.

:::{definition} stitch
Merging the same app's records from multiple upstream sources into one canonical record, picking the best value for each field. The pipeline that does this is described in {doc}`/project/architecture/stitch`.
:::

Four sources contribute to the catalog today: Installomator, Homebrew Cask, AutoPkg, and Jamf App Installers.

(installomator)=

## Installomator

[Installomator](https://github.com/Installomator/Installomator) is the open-source tool many MacAdmins use to automate macOS app installs, usually wired up through Jamf Pro or another MDM. Each app it supports is described by a shell *label* (e.g. `googlechrome`, `slack`, `zoom`) that knows how to locate, download, and install the current version.

:::{definition} slug
A short, lowercase identifier for an app in the catalog, taken from its Installomator label name (e.g. `googlechrome`, `slack`, `zoom`). Slugs are what you pass to the API and CLI to look an app up.
:::

What it contributes
: The label slug set is Patcher's backbone for "is this app automatable." Patcher matches each Jamf patch title against the Installomator slug set, and titles that match get an `install_label` entry surfaced in reports and filters. Beyond the slug, a label can yield a concrete download URL, version string, and install method once its dynamic shell fragments are resolved (a Linux-ingest / macOS-runner step described in {doc}`/project/architecture/resolution`).

Coverage characteristics
: Broad coverage of common third-party Mac apps, maintained by an active community. The catch is that many labels compute their version and URL at runtime via shell, so the static label alone does not always carry a version. Apple-managed software (macOS, Safari, Xcode) and license-gated runtimes (Oracle Java, Eclipse Temurin) are intentionally outside Installomator's useful scope for patch tracking.

:::{seealso}
Matching against labels happens during the export/fetch flow. How to disable it is covered in the {doc}`export guide </guides/usage/cli>`, and the matching algorithm itself (direct, normalized, and fuzzy passes) is documented in the {mod}`patcher.core.matching` reference.
:::

## Homebrew Cask

[Homebrew Cask](https://github.com/Homebrew/homebrew-cask) is the macOS GUI-application arm of the [Homebrew](https://brew.sh) package manager. Each *cask* is a Ruby definition naming an app, its current version, and a download URL, published as a single queryable JSON catalog by the Homebrew API.

What it contributes
: A reliable, machine-readable current version and download URL for a large set of GUI Mac apps, keyed by a cask token. This is often the cleanest version signal in the stitch because Cask metadata is static JSON rather than runtime-computed shell. It also feeds the API's label-generation feature, where Cask version and URL data is projected into an Installomator-shaped label.

Coverage characteristics
: Strong coverage of consumer and developer GUI apps with consistent, parseable version data. The notable gap is the developer Team ID: Cask metadata does not include `expectedTeamID`, so a Cask-only app produces a label-generation warning for that field. Casks also skew toward freely downloadable software; enterprise apps gated behind a login or licensing portal are underrepresented.

## AutoPkg

[AutoPkg](https://github.com/autopkg/autopkg) is an automation framework for downloading and packaging Mac software, driven by community-maintained *recipes*. A recipe is an XML/plist pipeline describing how to fetch and package one app.

What it contributes
: Coverage signal and packaging provenance. Patcher's ingest clones recipe repositories and parses them for app metadata, recording which apps have an AutoPkg path and which recipes exist for them. For an app already covered by another source, AutoPkg presence is a useful "there is a packaging recipe for this" indicator that admins can act on.

Coverage characteristics
: Very broad in breadth (the recipe ecosystem is large) but uneven in structured depth. Recipes describe *how to build* a package more than they assert a single current version, so AutoPkg's contribution leans toward existence-and-pointer signal rather than a clean version string. Recipes outside the core `autopkg/` org may not be ingested, so community-fork recipes can be missed.

## Jamf App Installers

[Jamf App Installers](https://learn.jamf.com/r/en-US/jamf-pro-documentation-current/App_Installers) (JAI) is Jamf Pro's first-party managed-app deployment catalog, where Jamf curates and maintains installers for a set of common titles directly within Jamf Pro.

What it contributes
: A coverage indicator sourced from the public JAI software-title catalog on `learn.jamf.com`. For each title, Patcher records that a Jamf-maintained App Installer exists. For admins on Jamf Pro, this answers "can I deploy this through Jamf's own managed-app path instead of rolling my own."

Coverage characteristics
: A curated, vendor-maintained set, so it is narrower than the community sources but carries Jamf's own maintenance behind each entry. The structured depth is the thinnest of the four: the public catalog is scraped for the title list (a coverage signal), not for bundle IDs, versions, or download URLs. Richer JAI data lives behind the undocumented tenant catalog endpoint, which requires Jamf Pro tenant access Patcher does not assume.

## How the Sources Combine

No single source is authoritative for every field. The catalog's value is the merge: a download URL from Cask, an install label from Installomator, a packaging recipe from AutoPkg, and a Jamf-managed deployment indicator can all describe the same app. When sources disagree on the current version, that disagreement is surfaced as *drift* rather than silently picking a winner.

:::{definition} drift
When two or more sources report a different "latest" version for the same app. Patcher surfaces the disagreement rather than picking a winner, which is a strong signal that a label has fallen behind upstream.
:::


```{seealso}
{doc}`/project/architecture/index`
: Where the ingest, stitch, and serving layers sit in the API service.

{doc}`/project/architecture/stitch` & {doc}`/project/architecture/resolution`
: The stitching and resolution pipelines.
```
