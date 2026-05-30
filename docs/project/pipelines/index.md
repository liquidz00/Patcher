---
layout: focused
description: "Patcher's data pipelines: stitching upstream sources into canonical app records, and resolving Installomator's dynamic shell fragments into concrete values."
---

# Pipelines

:::{rst-class} lead
The two cooperating pipelines that turn raw upstream signals into the catalog API.
:::

---

The Patcher catalog you query via the {doc}`REST API </reference/api/endpoints>`, the {doc}`MCP server </getting-started/mcp>`, or the {class}`~patcher.clients.patcher_api.PatcherAPIClient` library is built by two cooperating pipelines. These pages describe each in plain language so you can follow what's happening between "an upstream source published a new version" and "the catalog reflects it."

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Stitching`
:link: stitch
:link-type: doc

How the five upstream sources (Installomator, Homebrew Cask, AutoPkg, Mac App Store, Jamf App Installers) merge into one canonical app record per app.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Resolution`
:link: resolution
:link-type: doc

How Installomator labels' dynamic shell fragments become concrete download URLs and version strings, via a Linux-ingest / macOS-runner producer-consumer split.
:::

::::

```{toctree}
:hidden:

stitch
resolution
```
