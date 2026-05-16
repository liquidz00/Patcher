---
layout: landing
---

<div align="center">

```{image} _static/patcher-banner-readme.svg
:width: 750
```

![](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)
![](https://img.shields.io/github/v/release/liquidz00/Patcher?color=orange)
![](https://github.com/liquidz00/patcher/actions/workflows/pytest.yml/badge.svg)
![](https://img.shields.io/pypi/v/patcherctl?color=yellow)
![](https://img.shields.io/badge/macOS-10.13%2B-blueviolet?logo=apple&logoSize=auto)

</div>

# Patcher Documentation

:::{rst-class} lead
Simplified patch management and reporting.
:::

:::{container} buttons
[Get Started](getting-started/install.md)
[GitHub](https://github.com/liquidz00/Patcher)
:::

## License

Patcher is licensed under the Apache License 2.0. See the [LICENSE](https://github.com/liquidz00/Patcher/blob/main/LICENSE) file for details.

<!-- TODO -->


<!-- ## Features

- **Real-Time Patch Information Export**: Quickly extract up-to-date patch data for analysis.
- **Excel Spreadsheet Integration**: Seamlessly export patch information into Excel for in-depth analysis and record-keeping.
- **PDF Reporting**: Generate neatly formatted PDFs for easy sharing and documentation of patch statuses.
- **Customization Options**: Tailor the tool to match your organizations branding scheme with custom fonts and logo support.
- **Analysis**: Quickly analyze Patch Reports to identify which software titles may need some extra TLC.

::::{grid} 1 1 2 2
:gutter: 2
:padding: 2 2 0 0
:class-container: sd-text-center

:::{grid-item-card} {fas}`rocket;sd-text-primary` Getting Started
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Connect Patcher to your Jamf Pro instance and run your first patch report.

+++

```{button-ref} getting-started/index
:ref-type: myst
:click-parent:
:color: primary
:expand:

Get Started
```

:::

:::{grid-item-card} {fas}`terminal;sd-text-primary` Usage
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Day-to-day commands and library calls: export, analyze, reset, automate.

+++

```{button-ref} usage/index
:ref-type: myst
:click-parent:
:color: primary
:expand:

Browse Usage
```

:::

:::{grid-item-card} {fas}`puzzle-piece;sd-text-primary` Integrations
:class-card: sd-card
:class-title: patcher-title
:shadow: md

How Patcher enriches Jamf data with Installomator, Homebrew Cask, AutoPkg, and more.

+++

```{button-ref} integrations/index
:ref-type: myst
:click-parent:
:color: primary
:expand:

See Integrations
```

:::

:::{grid-item-card} {fas}`lightbulb;sd-text-primary` Concepts
:class-card: sd-card
:class-title: patcher-title
:shadow: md

How Patcher works under the hood: architecture, matching logic, local data storage.

+++

```{button-ref} concepts/index
:ref-type: myst
:click-parent:
:color: primary
:expand:

Learn Concepts
```

:::
:::: -->

```{toctree}
:caption: Getting Started
:hidden:

getting-started/install
getting-started/jamf-api
getting-started/setup/index
getting-started/customization
```

```{toctree}
:caption: Usage
:hidden:

usage/export
usage/analyze
usage/reset
usage/automation
```

```{toctree}
:caption: Integrations
:hidden:

integrations/installomator
integrations/homebrew-cask
integrations/autopkg
integrations/jamf-app-installers
```

```{toctree}
:caption: Concepts
:hidden:

concepts/architecture
concepts/data-storage
```

```{toctree}
:caption: Patcher API
:hidden:

api/endpoints
api/examples
```

```{toctree}
:caption: Support
:hidden:

support/faq
support/troubleshooting
```

```{toctree}
:caption: Reference
:hidden:

reference/index
```
