---
description: "Reference for patcher_api.catalog — SHA-256-backed ETag helpers for the catalog file."
---

# catalog

Helpers that compute and cache the catalog file's SHA-256 so the FastAPI middleware can attach a weak ETag to every `/apps*` response. The hash changes exactly when the catalog deploys (typically once per day on the refresh schedule) and never otherwise, which makes it a perfect cache key for both Cloudflare and revalidating clients.

```{eval-rst}
.. automodule:: patcher_api.catalog
   :members:
```
