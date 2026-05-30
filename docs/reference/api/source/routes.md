---
description: "Reference for patcher_api.routes — FastAPI route modules for public catalog reads and admin upserts."
---

# routes

FastAPI route modules registered on the main app. Public reads (`/apps`, `/health`) are open; admin writes (`/admin/*`) are gated by a shared secret and rate-limited per IP.

## apps

Public catalog reads. List + filter, per-slug fetch, per-source payloads, drift detection, and label generation.

```{eval-rst}
.. automodule:: patcher_api.routes.apps
   :members:
```

## admin

Write surface used by the macOS resolver runner to push resolved label values back into the catalog. Token-gated and fail-closed when no token is configured.

```{eval-rst}
.. automodule:: patcher_api.routes.admin
   :members:
```
