---
html_theme.sidebar_secondary.remove: True
---

# User Guide

Patcher is an innovative tool designed for Mac Admins. Leveraging the Jamf Pro API, Patcher streamlines the process of fetching patch management data and generating comprehensive reports, facilitating efficient tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

## Features

- **Real-Time Patch Information Export**: Quickly extract up-to-date patch data for analysis.
- **Excel Spreadsheet Integration**: Seamlessly export patch information into Excel for in-depth analysis and record-keeping.
- **PDF Reporting**: Generate neatly formatted PDFs for easy sharing and documentation of patch statuses.
- **Customization Options**: Tailor the tool to match your organizations branding scheme with custom fonts and logo support.
- **Analysis**: Quickly analyze Patch Reports to identify which software titles may need some extra TLC.

* * *

::::{grid} 2
:class-container: sd-text-left
:gutter: 3
:margin: 2

:::{grid-item-card} {fas}`rocket;sd-text-primary`  Getting Started
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Learn about prerequisites and installation. 
```{toctree}
:caption: Getting Started
:maxdepth: 2
:hidden:

prereqs
install
```

+++
```{button-ref} prereqs
:ref-type: ref
:color: secondary
:expand:

Getting Started
```

:::

:::{grid-item-card} {fas}`gear;sd-text-primary`  Setup
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Follow detailed instructions to configure Patcher.
```{toctree}
:caption: Setup
:maxdepth: 2
:hidden:

setup_assistant
jamf_deployment
schedulereports
```

+++
```{button-ref} setup
:ref-type: ref
:color: secondary
:expand:

Setup
```
:::

:::{grid-item-card} {fas}`book;sd-text-primary`  Usage
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Discover how to use Patcher and its features.
```{toctree}
:caption: Usage
:maxdepth: 2
:hidden:

usage
analyze
export
reset
customize_reports
```

+++
```{button-ref} usage
:ref-type: ref
:color: secondary
:expand:

Usage
```
:::

:::{grid-item-card} {fas}`search;sd-text-primary` Support & Troubleshooting
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Find solutions to issues and FAQs.
```{toctree}
:caption: Support & Troubleshooting
:maxdepth: 2
:hidden:

troubleshooting
faq
```

+++
```{button-ref} support
:ref-type: ref
:color: secondary
:expand:

Support & Troubleshooting
```
:::

::::
