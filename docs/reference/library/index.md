---
layout: focused
description: "The four library classes most callers import: PatcherClient, PatcherAPIClient, JamfClient, and InstallomatorClient."
---

# Library Classes

:::{rst-class} lead
The package surface most callers import. Start here for the four classes you'll instantiate.
:::

---

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `PatcherClient`
:link: patcher_client
:link-type: doc

The headline class for most library callers. Composes `JamfClient`, `PatcherAPIClient`, and `DataManager` behind one async context manager and exposes `fetch_patches`, `analyze`, and report exports.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `PatcherAPIClient`
:link: patcher_api_client
:link-type: doc

Typed wrapper around `api.patcherctl.dev`. Returns Pydantic models (`App`, `AppSources`, `GeneratedLabel`) for list, filter, per-source, and label-generation reads.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `JamfClient`
:link: jamf_client
:link-type: doc

Async client for the Jamf Pro API. Patch titles, device inventory, OS versions, and OAuth token refresh — the only place Patcher reaches into your Jamf instance.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Installomator`
:link: installomator
:link-type: doc

Direct read access to the Installomator label registry on GitHub. Useful when you need raw label scripts; the matching pipeline itself lives at module level in `patcher.core.matching`.
:::
::::

```{toctree}
:hidden:

patcher_client
patcher_api_client
jamf_client
installomator
```
