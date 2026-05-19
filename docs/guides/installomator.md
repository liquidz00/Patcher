---
description: "How Patcher matches Jamf titles against Installomator labels. Covers the three-pass matching algorithm, unmatched-apps review, and toggling the integration."
---

(installomator)=

# Installomator Integration

:::{rst-class} lead
Each Jamf patch title gets a flag for "an Installomator label exists for this app" so reports can highlight what's automation-ready and what isn't.
:::

[Installomator](https://github.com/Installomator/Installomator) is an open-source tool for automated software installation on macOS, widely used by MacAdmins to streamline application deployment via Jamf Pro and other MDMs. Patcher matches each Jamf patch title against Installomator's label catalog; titles that match show up with an `install_label` entry on the {class}`~patcher.core.models.patch.PatchTitle`, which downstream filters and report columns use to surface "this app has an automation path."

:::{admonition} Disclaimer
:class: warning

While Patcher matches titles as accurately as possible, **Installomator is the source of truth** for label definitions. If you're unsure about a match, verify the label directly in the [Installomator repository](https://github.com/Installomator/Installomator).
:::

## Label cache

Each Installomator label is fetched once and written to `~/Library/Application Support/Patcher/.labels/<label>.sh`. Subsequent runs read from disk and skip the HTTP call entirely. The discovery list (Installomator's `Labels.txt`) is also fetched once per `patcherctl` process and held in memory for the duration of that run; it is not written to disk.

There is no automatic expiry. To refresh the cache (e.g. to pick up a newly-added Installomator label), delete the `.labels/` directory and re-run `patcherctl`:

```bash
rm -rf ~/Library/Application\ Support/Patcher/.labels
```

Cache size is bounded by the number of labels you've matched against. Typical fleets see 50–200 cached fragments at a few KB each, so the directory stays well under 1 MB.

## How matching works

When matching a Jamf software title against the local label set, Patcher tries three strategies in order:

1. **Direct match.** The software title's name (or any `appName` returned by Jamf) is compared case-insensitively against Installomator label names. Implemented by {meth}`~patcher.clients.installomator.InstallomatorClient._match_directly`.
2. **Fuzzy match.** If no direct hit, [`rapidfuzz`](https://rapidfuzz.github.io/RapidFuzz/) computes a similarity score against all labels. The best-scoring label above the threshold wins. Implemented by {meth}`~patcher.clients.installomator.InstallomatorClient._match_fuzzy`.
3. **Normalized match.** As a last resort, the title name is normalized (punctuation stripped, lowercased) before comparison, so `Node.js` becomes `nodejs` and matches the label of the same name.

The full algorithm (including how multiple `appName` values are resolved against multiple labels per title) is in {meth}`~patcher.clients.installomator.InstallomatorClient.match`.

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

All `appName` values are collected alongside the software title name. The full set is what Patcher hands to the matching strategies above.

## Unmatched applications

Software titles that don't match any label after all three strategies are written to `~/Library/Application Support/Patcher/unmatched_apps.json`:

```json
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

This file lets you spot gaps and either {ghwiki}`author new Installomator labels <Installomator:Label Variables Reference#Building a new label>` for the missing apps or report missing mappings upstream. If a label is later added, the entry will be removed automatically on the next match.

When an app has multiple matching labels (e.g. `zulujdk8`, `zulujdk9`), all labels are stored in the {class}`~patcher.core.models.patch.PatchTitle`'s `install_label` list.

## Ignored software titles

Some titles are explicitly skipped because they're not patchable through Installomator. Typically system software, deprecated apps, or anything that requires manual licensing intervention.

```python
IGNORED_TITLES = [
    "Apple macOS *",
    "Oracle Java SE *",
    "Eclipse Temurin *",
    "Apple Safari",
    "Apple Xcode",
    "Microsoft Visual Studio",
]
```

:::{warning}
Any title matching this list **won't be matched** to an Installomator label, even if a label exists.
:::

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

(disabling_installomator_support)=

## Disabling Installomator support

If Installomator doesn't fit your environment, turn the integration off entirely. When disabled, no catalog calls are made and the `install_label` field on every {class}`~patcher.core.models.patch.PatchTitle` stays empty.

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

Patcher reads `enable_installomator` from its property list. Set it to `false`:

```console
$ defaults write ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist enable_installomator -bool false
```

The next `patcherctl` invocation skips Installomator-sourced matching entirely.
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

With `enable_installomator=False`, `PatcherClient.api` is `None` and `match_titles` is never called.
:::

::::
