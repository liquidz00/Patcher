---
description: "Reference for patcher_api.catalog — the version token backing the catalog ETag."
---

# catalog

Computes and caches the catalog version token so the FastAPI middleware can attach a weak ETag to every `/apps*` response. The token is the catalog's newest mutation timestamp (latest ingest plus the latest macOS resolver write), so it changes exactly when the served data changes and never otherwise, which makes it a perfect cache key for both Cloudflare and revalidating clients.

```{eval-rst}
.. autofunction:: patcher_api.catalog.recompute_catalog_version
```
