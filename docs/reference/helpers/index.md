---
layout: focused
description: "Cross-cutting utility classes: structured logging and the exception hierarchy."
---

# Helpers

:::{rst-class} lead
Utilities used throughout the codebase: structured logging and exceptions.
:::

---

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Exceptions`
:link: exceptions
:link-type: doc

Patcher's exception hierarchy. The base `PatcherError`, transport-specific errors like `APIResponseError`, and warning classes such as `InstallomatorWarning` emitted via Python's `warnings` module.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Logger`
:link: logger
:link-type: doc

`PatcherLog` configures the rotating file handler under `~/Library/Application Support/Patcher/logs/`; `LogMe` is the per-module helper callers use to scope output.
:::
::::

```{toctree}
:hidden:

exceptions
logger
```
