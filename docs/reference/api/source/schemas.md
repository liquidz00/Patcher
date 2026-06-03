---
description: "Reference for patcher_api.schemas — Pydantic models returned by the API."
---

# schemas

Pydantic models the API uses for response serialization (and a few request bodies). One module per source's payload shape, plus shared schemas for apps, drift, and labels.

## App

```{eval-rst}
.. autoclass:: patcher_api.schemas.app.InstallMethod
   :members:

.. autoclass:: patcher_api.schemas.app.App
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## Sources (composite payload)

```{eval-rst}
.. autoclass:: patcher_api.schemas.sources.InstallomatorSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.sources.HomebrewCaskSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.sources.AutopkgRecipeEntry
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.sources.AutopkgSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.sources.MasSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.sources.JamfAppInstallerSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.sources.AppSources
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## Drift

```{eval-rst}
.. autoclass:: patcher_api.schemas.drift.SourceVersion
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.drift.DriftEntry
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.drift.DriftResponse
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## Labels

```{eval-rst}
.. autoclass:: patcher_api.schemas.labels.GenerateLabelResponse
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

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
.. autoclass:: patcher_api.schemas.jamf_app_installers.JaiMediaSource
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.jamf_app_installers.JaiTitle
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields

.. autoclass:: patcher_api.schemas.jamf_app_installers.JaiTitlePage
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```

## Mac App Store

```{eval-rst}
.. autoclass:: patcher_api.schemas.mas.MasLookupRecord
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```
