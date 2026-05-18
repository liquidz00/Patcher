(installomator)=

# Installomator

:::{rst-class} lead
How Patcher cross-references Jamf software titles with Installomator's label catalog to surface automation-ready apps.
:::

[Installomator](https://github.com/Installomator/Installomator) is an open-source tool for automated software installation on macOS, widely used by MacAdmins to streamline application deployment via Jamf Pro and other MDMs. Patcher cross-references Jamf patch titles against Installomator's catalog of labels, surfacing which of your tracked software has an automation-ready install path.

:::{admonition} Disclaimer
:class: warning

While Patcher matches titles as accurately as possible, **Installomator is the source of truth** for label definitions. If you're unsure about a match, verify the label directly in the [Installomator repository](https://github.com/Installomator/Installomator).
:::

## How matching works

Labels are stored locally under `~/Library/Application Support/Patcher/.labels/` after the first run, reducing network overhead on subsequent matches. Patcher refreshes the local cache periodically.

When matching a Jamf software title against the local label set, Patcher tries three strategies in order:

1. **Direct match.** The software title's name (or any `appName` returned by Jamf) is compared case-insensitively against Installomator label names. Implemented by {meth}`~patcher.core.installomator.InstallomatorClient._match_directly`.
2. **Fuzzy match.** If no direct hit, [`rapidfuzz`](https://rapidfuzz.github.io/RapidFuzz/) computes a similarity score against all labels. The best-scoring label above the threshold wins. Implemented by {meth}`~patcher.core.installomator.InstallomatorClient._match_fuzzy`.
3. **Normalized match.** As a last resort, the title name is normalized (punctuation stripped, lowercased) before comparison, so `Node.js` becomes `nodejs` and matches the label of the same name.

The full algorithm (including how multiple `appName` values are resolved against multiple labels per title) is in {meth}`~patcher.core.installomator.InstallomatorClient.match`.

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

This file lets you spot gaps and either [author new Installomator labels](https://github.com/Installomator/Installomator/wiki/Label-Variables-Reference#building-a-new-label) for the missing apps or report missing mappings upstream. If a label is later added, the entry will be removed automatically on the next match.

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

- **Apple software (macOS, Safari, Xcode):** managed via MDM or Apple's software update mechanism.
- **Java / Eclipse Temurin:** typically require manual licensing and security review.
- **Microsoft Visual Studio:** refers to the full Visual Studio for Mac IDE, [deprecated by Microsoft in August 2024](https://devblogs.microsoft.com/visualstudio/visual-studio-for-mac-retirement-announcement/). *Visual Studio Code is unaffected and remains supported.*

(disabling_installomator_support)=

## Disabling Installomator support

If Installomator doesn't fit your environment, you can turn the integration off entirely. Patcher reads `enable_installomator` from its property list. Set it to `false` to bypass label downloads and matching:

```console
$ defaults write ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist enable_installomator -bool false
```

When disabled:

- Labels are neither downloaded nor cached.
- Software-title matching does not run; the `install_label` field on every {class}`~patcher.core.models.patch.PatchTitle` stays empty.

Library callers can achieve the same by constructing `PatcherClient` with `enable_installomator=False`:

```python
patcher = PatcherClient(
    client_id=...,
    client_secret=...,
    server=...,
    enable_installomator=False,
)
```
