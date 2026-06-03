---
description: "Reference for patcher_api.stitch — merges per-source rows into canonical app records."
---

# stitch

Walks the per-source detail rows for each tracked app and projects them into the canonical `apps` table. Inputs are heterogeneous (Installomator labels, Homebrew Cask JSON, AutoPkg recipes, Jamf App Installers metadata, Mac App Store entries); outputs are normalized fields the public catalog serves. For the conceptual overview see {doc}`/project/architecture/stitch`.

```{eval-rst}
.. autofunction:: patcher_api.stitch.stitch_catalog
```
