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

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `TerminalLogger`
:link: terminal_logger
:link-type: doc

Click-backed adapter onto `PatcherLog`. Adds colored, level-prefixed bash lines on top of the always-present file log when the CLI installs its handler.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `UIConfigManager`
:link: ui_manager
:link-type: doc

CLI-side bridge between branding and the property list. Reads and writes `UserInterfaceSettings` (header, footer, fonts, logo, header color) for PDF and HTML rendering.
:::
::::

```{toctree}
:hidden:

fonts
setup
terminal_logger
ui_manager
```
