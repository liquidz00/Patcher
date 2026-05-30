---
description: "Reference for patcher_api.ingest — per-source ingest modules pulling upstream data into the catalog."
---

# ingest

One module per upstream source. Each pulls data from the upstream (HTTP, git clone, parsed catalog page) and writes per-app rows into `app_source_details` for the stitch pipeline to consume. Run from `scripts/ingest.py` on the refresh schedule.

## Homebrew Cask

```{eval-rst}
.. automodule:: patcher_api.ingest.homebrew
   :members:
```

## AutoPkg

```{eval-rst}
.. automodule:: patcher_api.ingest.autopkg
   :members:
```

## Jamf App Installers

```{eval-rst}
.. automodule:: patcher_api.ingest.jamf_app_installers
   :members:
```

## Mac App Store

```{eval-rst}
.. automodule:: patcher_api.ingest.mas
   :members:
```
