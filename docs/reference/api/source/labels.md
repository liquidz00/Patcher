---
description: "Reference for patcher_api.labels — projects an app record into an Installomator-shaped label fragment."
---

# labels

Builds an Installomator label fragment from an app's stitched record plus its per-source payloads. Used by the `POST /apps/{slug}/generate-label` endpoint. The fallback chain picks the best available value for each field (`name`, `downloadURL`, `expectedTeamID`, etc.) across Installomator, Homebrew Cask, and Jamf App Installers, with explicit warnings when a field can't be sourced cleanly.

```{eval-rst}
.. automodule:: patcher_api.labels
   :members:
```
