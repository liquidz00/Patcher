---
html_theme.sidebar_secondary.remove: True
---

# User Guide

Patcher is an innovative tool designed for Mac Admins. Leveraging the Jamf Pro API, Patcher streamlines the process of fetching patch management data and generating comprehensive reports, facilitating efficient tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

:::
### Features
:::

- **Real-Time Patch Information Export**: Quickly extract up-to-date patch data for analysis.
- **Excel Spreadsheet Integration**: Seamlessly export patch information into Excel for in-depth analysis and record-keeping.
- **PDF Reporting**: Generate neatly formatted PDFs for easy sharing and documentation of patch statuses.
- **Customization Options**: Tailor the tool to match your organizations branding scheme with custom fonts and logo support.
- **Analysis**: Quickly analyze Patch Reports to identify which software titles may need some extra TLC.

* * *

::::{grid} 1 1 1 3
:gutter: 2
:padding: 2 2 0 0
:class-container: sd-text-left

:::{grid-item-card}
:class-card: sd-text-left

```{toctree}
:maxdepth: 2
:caption: Getting Started

prereqs
jamf_deployment
install
```
:::

:::{grid-item-card}
:class-card: sd-text-left

```{toctree}
:maxdepth: 2
:caption: Setup

setup_assistant
customize_reports
```
:::

:::{grid-item-card}
:class-card: sd-text-left

```{toctree}
:maxdepth: 2
:caption: Command Options

usage
analyze
export
reset
```
:::

::::
