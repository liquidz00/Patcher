---
layout: focused
description: "Patcher API endpoint reference and end-to-end examples for the public catalog at api.patcherctl.dev."
---

# Patcher API

:::{rst-class} lead
Curated app catalog sourced from **Installomator**, **Homebrew**, **AutoPkg**, and more.
:::

---

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Endpoints`
:link: endpoints
:link-type: doc

HTTP-level reference for every path on `api.patcherctl.dev`. Covers list filters, per-source payloads, label generation, ETag caching semantics, and where to grab the OpenAPI schema.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Examples`
:link: examples
:link-type: doc

Worked `curl` and `PatcherAPIClient` walkthroughs for the common reads. Pagination, source filtering, ETag revalidation, and the error envelopes you'll see in practice.
:::
::::

```{toctree}
:hidden:

endpoints
examples
```
