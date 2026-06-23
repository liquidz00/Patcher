---
description: "Reference for patcher_api.routes — FastAPI route modules for public catalog reads and admin upserts."
---

# routes

FastAPI route modules registered on the main app. Public reads (`/apps`, `/health`) are open; admin writes (`/admin/*`) are gated by a shared secret and rate-limited per IP.

## apps

Public catalog reads. List + filter, per-slug fetch, per-source payloads, drift detection, and label generation.

```{eval-rst}
.. autofunction:: patcher_api.routes.apps.list_apps

.. autofunction:: patcher_api.routes.apps.list_drift

.. autofunction:: patcher_api.routes.apps.get_app

.. autofunction:: patcher_api.routes.apps.get_app_sources

.. autofunction:: patcher_api.routes.apps.get_app_drift

.. autofunction:: patcher_api.routes.apps.generate_label
```

## admin

Write surface used by the macOS worker to push resolved label values back into the catalog. Token-gated and fail-closed when no token is configured.

```{eval-rst}
.. autoclass:: patcher_api.routes.admin.ResolvedIngestSummary
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.routes.admin.UnresolvedLabels
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autofunction:: patcher_api.routes.admin.require_admin

.. autofunction:: patcher_api.routes.admin.list_unresolved_labels

.. autofunction:: patcher_api.routes.admin.ingest_resolved_labels
```
