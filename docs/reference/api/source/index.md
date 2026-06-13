---
layout: focused
description: "Source-level reference for patcher_api: stitch pipeline, drift detection, label builder, ingest modules, Installomator subsystem, FastAPI routes, and Pydantic schemas."
---

# Source Reference

:::{rst-class} lead
Module-level autodoc for the `patcher_api` codebase.
:::

---

Reference docs for the modules that power `api.patcherctl.dev`. Most callers don't need this; the {doc}`HTTP endpoints </reference/api/endpoints>` and the {class}`~patcher.clients.patcher_api.PatcherAPIClient` library wrapper are the public surface. These pages are for contributors and anyone reading the API internals.

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `stitch`
:link: stitch
:link-type: doc

Merge upstream source rows into canonical app records.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `drift`
:link: drift
:link-type: doc

Cross-source version drift detection.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `labels`
:link: labels
:link-type: doc

Project app records into Installomator-shaped label fragments.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `catalog`
:link: catalog
:link-type: doc

SQLite-backed catalog hash and ETag helpers.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `ingest`
:link: ingest
:link-type: doc

Per-source ingest pipelines (Homebrew, AutoPkg, JAI).
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `installomator`
:link: installomator
:link-type: doc

Installomator label parser, dynamic-value resolver, and ingest entry point.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `routes`
:link: routes
:link-type: doc

FastAPI route modules: public catalog reads and admin upserts.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `schemas`
:link: schemas
:link-type: doc

Pydantic schemas returned by the API.
:::

::::

```{toctree}
:hidden:

stitch
drift
labels
catalog
ingest
installomator
routes
schemas
```
