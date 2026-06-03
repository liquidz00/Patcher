---
description: "Reference for patcher_api.ingest — per-source ingest modules pulling upstream data into the catalog."
---

# ingest

One module per upstream source. Each pulls data from the upstream (HTTP, git clone, parsed catalog page) and writes per-app rows into `app_source_details` for the stitch pipeline to consume. Run from `scripts/ingest.py` on the refresh schedule.

## Homebrew Cask

```{eval-rst}
.. autofunction:: patcher_api.ingest.homebrew.fetch_homebrew_casks

.. autofunction:: patcher_api.ingest.homebrew.ingest_homebrew_casks
```

## AutoPkg

```{eval-rst}
.. autofunction:: patcher_api.ingest.autopkg.fetch_autopkg_index

.. autofunction:: patcher_api.ingest.autopkg.ingest_autopkg_index
```

## Jamf App Installers

```{eval-rst}
.. autofunction:: patcher_api.ingest.jamf_app_installers.fetch_jai_titles

.. autofunction:: patcher_api.ingest.jamf_app_installers.fetch_jai_catalog

.. autofunction:: patcher_api.ingest.jamf_app_installers.ingest_jai_titles
```

## Mac App Store

```{eval-rst}
.. autofunction:: patcher_api.ingest.mas.fetch_mas_lookup

.. autofunction:: patcher_api.ingest.mas.ingest_mas_apps
```
