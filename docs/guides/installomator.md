---
description: "How Patcher matches Jamf titles against Installomator labels via the Patcher API catalog. Covers the matching algorithm, unmatched-apps review, ignored titles, and disabling the integration."
---

(installomator)=

# Installomator Integration

:::{rst-class} lead
Highlighting what's automation-ready and what isn't.
:::

---

[Installomator](https://github.com/Installomator/Installomator) is the open-source tool a lot of MacAdmins use to automate macOS app installs, usually wired up through Jamf Pro or another MDM. Patcher matches each Jamf patch title against Installomator's label catalog; titles that match get an `install_label` entry on the {class}`~patcher.core.models.patch.PatchTitle`, and downstream filters and report columns use that to surface "this one has an automation path; this one you're installing by hand."

:::{admonition} Disclaimer
:class: warning

While Patcher matches titles as accurately as possible, **Installomator is the source of truth** for label definitions. If you're unsure about a match, verify the label directly in the [Installomator repository](https://github.com/Installomator/Installomator).
:::

## How matching works

`PatcherClient.fetch_patches` calls {func}`~patcher.core.matching.match_titles` to enrich each Jamf patch title with Installomator metadata. The slug set comes from the Patcher API catalog (one HTTP call to `api.patcherctl.dev/apps?source=installomator&limit=1000`) rather than fetching `Labels.txt` and per-label `.sh` fragments from GitHub directly. Match quality is the same; latency is lower and there is no per-label disk cache for the normal flow to maintain.

For each patch title, matching runs in three stages:

1. **Direct + normalized match.** Each Jamf-side app name is compared against the slug set both case-insensitively (`Google Chrome` → `google chrome`) and in a normalized form with spaces and dots stripped (`Node.js` → `nodejs`). Both happen in one pass via {func}`~patcher.core.matching.match_directly`.
2. **Fuzzy match.** If no direct hit, [`rapidfuzz`](https://rapidfuzz.github.io/RapidFuzz/) scores each app name against the full slug set; matches at or above the 85 threshold are kept. {func}`~patcher.core.matching.match_fuzzy`.
3. **Second pass on the patch title text.** Titles still unmatched after stages 1–2 get one more attempt using the *patch title* itself (not just the Jamf-side app names): normalized first, then fuzzy. Catches cases where the Jamf app names diverged from the title but the title itself maps cleanly to a label.

Anything still unmatched after stage 3 is written to `~/Library/Application Support/Patcher/unmatched_apps.json` for review, and an `InstallomatorWarning` is emitted via Python's `warnings` module so library callers can catch / escalate programmatically. The CLI installs `warnings.simplefilter("always", InstallomatorWarning)` so end users always see the message.

When an app matches multiple labels (e.g. `zulujdk8`, `zulujdk9`), all matched labels are attached to the `PatchTitle.install_label` list.

### Why matching can be tricky

Naming conventions vary widely between Jamf, the macOS bundle ID, and Installomator. Take Zoom:

- Jamf software title: **Zoom Client for Meetings**
- macOS application name: `zoom.us.app`
- Installomator labels: `zoom`, `zoomclient`, `zoomgov`, …

(app_name_response)=

To handle this, Patcher pulls Application Names from Jamf via the `/api/v2/patch-software-title-configurations/{title_id}/definitions` endpoint. The response looks roughly like:

```{code-block} json
:caption: [Jamf Developer Docs](https://developer.jamf.com/jamf-pro/reference/get_v2-patch-software-title-configurations-id-definitions)

{
  "totalCount": 1,
  "results": [
    {
      "version": "10.37.0",
      "minimumOperatingSystem": "12.0.1",
      "releaseDate": "2010-12-10 13:36:04",
      "rebootRequired": false,
      "killApps": [{"appName": "Firefox"}],
      "standalone": false,
      "absoluteOrderId": "1"
    }
  ]
}
```

All `appName` values are collected alongside the software title name. The full set is what `match_directly` and `match_fuzzy` evaluate.

## Unmatched applications

Software titles that don't match any label after all three stages are written to `~/Library/Application Support/Patcher/unmatched_apps.json`:

```{code-block} json
:caption: ~/Library/Application Support/Patcher/unmatched_apps.json

[
    {
        "Patch": "Appium",
        "App Names": ["Appium"]
    },
    {
        "Patch": "Adobe Illustrator",
        "App Names": ["Adobe Illustrator"]
    }
]
```

Each entry contains:

- **`Patch`**: the `title` attribute of the {class}`~patcher.core.models.patch.PatchTitle`.
- **`App Names`**: the Application Names extracted from the [Jamf API response](#app_name_response).

This file lets you spot gaps and either {ghwiki}`author new Installomator labels <Installomator:Label Variables Reference#Building a new label>` for the missing apps or report missing mappings upstream. The file is rewritten on every match run, so titles that gain a label upstream simply drop out next run.

## Ignored software titles

A small fixed list of titles is skipped before matching runs because they aren't patchable through Installomator. The list lives at module scope in `patcher.core.matching` as `_IGNORED_TITLES`:

```python
_IGNORED_TITLES = [
    "Apple macOS *",
    "Oracle Java SE *",
    "Eclipse Temurin *",
    "Apple Safari",
    "Apple Xcode",
    "Microsoft Visual Studio",
]
```

Patterns use `fnmatch` semantics, so `Apple macOS *` skips every Apple macOS title regardless of version. Skipped titles never get an `install_label` even if a corresponding label exists.

Reasoning:

::::{tab-set}

:::{tab-item} {iconify}`simple-icons:apple` Apple software
:sync: apple

`Apple macOS *`, `Apple Safari`, `Apple Xcode`. Managed via MDM or Apple's own software update mechanism. Patcher's `install_label` flow is built for third-party app patching; Apple's update infrastructure has different cadence and operational characteristics that the Installomator path wouldn't add value to.
:::

:::{tab-item} {iconify}`devicon:java` Java / Eclipse Temurin
:sync: java

`Oracle Java SE *`, `Eclipse Temurin *`. Typically require manual licensing and security review before deployment. Even when a public Installomator label exists, environments running Java usually have a dedicated package-management workflow gated on license compliance.
:::

:::{tab-item} {iconify}`simple-icons:visualstudio` Microsoft Visual Studio
:sync: vs

`Microsoft Visual Studio`. Refers to the full Visual Studio for Mac IDE, [deprecated by Microsoft in August 2024](https://devblogs.microsoft.com/visualstudio/visual-studio-for-mac-retirement-announcement/).

*Visual Studio Code is unaffected and remains supported.*
:::

::::

## Working with `InstallomatorClient` directly

If you only need to enumerate or fetch labels (without the Jamf side or the matching pipeline), use {class}`~patcher.clients.installomator.InstallomatorClient` directly. The client fetches Installomator's `Labels.txt` once per session (held in memory) and caches each fetched `.sh` fragment to `~/Library/Application Support/Patcher/.labels/<label>.sh` so subsequent reads skip the HTTP round-trip:

```python
from patcher import InstallomatorClient

iom = InstallomatorClient()
labels = await iom.list_available_labels()  # set of slug names from Labels.txt
firefox = await iom.get_label("firefox")    # parsed Label model
many = await iom.get_labels({"firefox", "googlechrome"})  # bulk fetch
```

To refresh that on-disk cache (e.g. to pick up a newly-added Installomator label), delete `~/Library/Application Support/Patcher/.labels/` and re-run.

The normal `patcherctl export` flow does **not** populate this cache; matching goes through the Patcher API catalog, not GitHub directly. The cache is only relevant if you call `InstallomatorClient` methods yourself.

(disabling_installomator_support)=

## Disabling Installomator support

If Installomator-style matching doesn't fit your environment, turn the catalog client off entirely. When disabled, no catalog calls are made and the `install_label` field on every {class}`~patcher.core.models.patch.PatchTitle` stays empty.

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

Patcher reads `enable_installomator` from its property list. Set it to `false`:

```console
$ defaults write ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist enable_installomator -bool false
```

The next `patcherctl` invocation skips the catalog match entirely.
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

Construct `PatcherClient` with `enable_installomator=False`. The plist value is ignored in favor of the explicit kwarg:

```python
patcher = PatcherClient(
    client_id=...,
    client_secret=...,
    server=...,
    enable_installomator=False,
)
```

With `enable_installomator=False`, `PatcherClient.api` is `None` and `match_titles` is never called from `fetch_patches`.
:::

::::
