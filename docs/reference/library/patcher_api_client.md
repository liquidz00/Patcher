---
description: "Reference for PatcherAPIClient: the typed client for the api.patcherctl.dev catalog."
---

# Patcher API Client

:::{seealso}
{doc}`/reference/api/endpoints` — the API surface this client wraps.
:::

```{eval-rst}
.. autoclass:: patcher.clients.patcher_api.PatcherAPIClient
   :members:
```

## Response models

Pydantic models that mirror the API's wire format. Returned from the client methods above; useful for type-hinting your own code.

```{eval-rst}
.. autoclass:: patcher.clients.patcher_api.App
   :members:

.. autoclass:: patcher.clients.patcher_api.AppSources
   :members:

.. autoclass:: patcher.clients.patcher_api.InstallomatorSource
   :members:

.. autoclass:: patcher.clients.patcher_api.HomebrewCaskSource
   :members:

.. autoclass:: patcher.clients.patcher_api.AutopkgSource
   :members:

.. autoclass:: patcher.clients.patcher_api.AutopkgRecipeEntry
   :members:

.. autoclass:: patcher.clients.patcher_api.MasSource
   :members:

.. autoclass:: patcher.clients.patcher_api.JamfAppInstallerSource
   :members:

.. autoclass:: patcher.clients.patcher_api.GeneratedLabel
   :members:

.. autoclass:: patcher.clients.patcher_api.DriftResponse
   :members:

.. autoclass:: patcher.clients.patcher_api.DriftEntry
   :members:

.. autoclass:: patcher.clients.patcher_api.SourceVersion
   :members:

.. autoclass:: patcher.clients.patcher_api.InstallMethod
   :members:
```
