---
layout: landing
# description:
description: "Simplified patch management reporting for macOS fleets on Jamf Pro. Open-source Python CLI and library; PDF, HTML, Excel, and JSON exports."
---
<div>

# Patcher

![](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)
![](https://img.shields.io/github/v/release/liquidz00/Patcher?color=orange)
![](https://github.com/liquidz00/patcher/actions/workflows/pytest.yml/badge.svg)
![](https://img.shields.io/pypi/v/patcherctl?color=yellow)
![](https://img.shields.io/badge/macOS-10.13%2B-blueviolet?logo=apple&logoSize=auto)

</div>

:::{rst-class} lead
A Python package and CLI for **patch analysis, reporting, and catalog access** on macOS fleets managed by Jamf Pro.
:::

:::{container} buttons
[Docs](getting-started/install.md)
[GitHub](https://github.com/liquidz00/Patcher)
:::

::::{grid} 1 1 2 3
:gutter: 2
:padding: 0

:::{grid-item-card} {iconify}`lucide:search` Patch analysis

Cross-reference Jamf Pro's patch-management view of your fleet against [Installomator](https://github.com/Installomator/Installomator), [Homebrew](https://github.com/Homebrew/brew), [AutoPkg](https://github.com/autopkg/autopkg), and [Jamf App Installers](https://learn.jamf.com/r/en-US/jamf-pro-documentation-current/App_Installers).
:::

:::{grid-item-card} {iconify}`lucide:file-bar-chart` Reporting

Export customizable reports in varying formats tailored to a tracked Jamf Pro instance.
:::

:::{grid-item-card} {iconify}`lucide:server` Catalog API

A community-facing {doc}`JSON API </api/endpoints>` stitching the same upstream sources into a single queryable surface.
:::
::::

## License

Patcher is licensed under the Apache License 2.0. See the [LICENSE](https://github.com/liquidz00/Patcher/blob/main/LICENSE) file for details.

<!-- TODO -->


```{toctree}
:caption: Getting Started
:hidden:

getting-started/install
getting-started/jamf-api
getting-started/setup
getting-started/customization
```

```{toctree}
:caption: Usage
:hidden:

usage/export
usage/analyze
usage/reset
usage/installomator
usage/library
usage/automation
```

```{toctree}
:caption: Patcher API
:hidden:

api/endpoints
api/examples
```

```{toctree}
:caption: Development & Support
:hidden:

contributing/index
support/data-storage
support/faq
support/troubleshooting
```

```{toctree}
:caption: Reference
:hidden:

reference/index
```
