---
description: "Reference for patcher_api.schemas — the API's ingest/upstream-parsing schemas."
---

# schemas

The API's ingest schemas — the shapes used to parse each source's native upstream
payload on the way *into* the catalog.

:::{seealso}
The catalog **response** schemas (`App`, `AppSources`, the per-source payloads,
`GeneratedLabel`, drift) now live in the shared `patcher.catalog.schemas` module
and are documented on the {doc}`/reference/library/patcher_api_client` page.
:::

## Shared base

`UpstreamModel` is the camelCase base every upstream payload schema inherits from (it is not Installomator-specific; Installomator's raw payload is stored as a dict rather than a typed model).

```{eval-rst}
.. autoclass:: patcher_api.schemas.base.UpstreamModel
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## Homebrew Cask

```{eval-rst}
.. autoclass:: patcher_api.schemas.homebrew.HomebrewCaskRecord
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## AutoPkg

```{eval-rst}
.. autoclass:: patcher_api.schemas.autopkg.AutopkgIndexEntry
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## Jamf App Installers

```{eval-rst}
.. autoclass:: patcher_api.schemas.jamf.JaiMediaSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.jamf.JaiTitle
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.jamf.JaiTitlePage
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```
