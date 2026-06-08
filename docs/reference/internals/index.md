---
layout: focused
description: "Implementation detail of the `patcherctl` CLI. Not part of the library's stable surface; documented for contributors reading or modifying the CLI."
---

# Internal Classes

:::{rst-class} lead
Implementation detail of `patcherctl`. Not part of the library's stable surface; documented for contributors reading or modifying the CLI.
:::

---

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Fonts`
:link: fonts
:link-type: doc

Bundled-font discovery and download. Resolves the Assistant Regular/Bold pair Patcher ships, with fallback when the user has set custom font paths under `UserInterfaceSettings`.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Setup`
:link: setup
:link-type: doc

First-run wizard. Drives credential entry, optional API role/client creation on the Jamf side, and writes setup state into the property list.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Console / Output`
:link: console
:link-type: doc

The CLI's terminal-output layer: Rich console singletons, the status spinner, table/diff/drift renderers, the error panel, and the click-backed log handler that adds colored, level-prefixed lines on top of the file log.
:::
::::

```{toctree}
:hidden:

fonts
setup
console
```
