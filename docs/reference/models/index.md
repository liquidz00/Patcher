---
layout: focused
description: "Pydantic data shapes returned by the library entry-point clients: PatchTitle, PatchDevice, Label, CaskMatch, UIConfig, AccessToken."
---

# Data Models

:::{rst-class} lead
Pydantic shapes returned by the library entry points. The objects you destructure in your own code.
:::

---

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Patch`
:link: patch
:link-type: doc

`PatchTitle` and `PatchDevice` — the report-shaped models `PatcherClient.fetch_patches` returns. Iterate these when you're building custom dashboards, alerting, or downstream exports.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `JamfModels`
:link: jamf_models
:link-type: doc

Pydantic shapes covering Jamf API integration. `JamfCredentials` for connection details; `ApiRoleModel` and `ApiClientModel` describe the role + client objects Patcher creates during Standard setup.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Label`
:link: label
:link-type: doc

Parsed Installomator label. Captures the fields Installomator's bash labels expose (download URL, expected team ID, type, etc.) as typed attributes.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `CaskMatch`
:link: cask
:link-type: doc

Homebrew Cask coverage stub attached to `PatchTitle.homebrew_cask` when `--homebrew` matching is enabled. The Cask analogue of `Label`; records the matched cask token, version, and download URL.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `UI`
:link: ui
:link-type: doc

`UIConfig` — the branding payload for PDF and HTML reports. Header text, footer text, font paths, logo path, header color.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Token`
:link: token
:link-type: doc

`AccessToken` — the OAuth bearer-token wrapper used by `JamfClient`. Wraps the secret value in `pydantic.SecretStr` so accidental `repr` or logging won't leak it.
:::
::::

```{toctree}
:hidden:

patch
jamf_models
label
cask
ui
token
```
