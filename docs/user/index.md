---
html_theme.sidebar_secondary.remove: True
---

# User Guide

The User Guide is designed to be your go-to resource for learning how to set up, customize, and utilize Patcher effectively. Whether you're just getting started or looking to dive deeper into some features, this guide is here to help each step of the way.

## What You'll Find Here

- **Getting Started**: Learn about prerequisites, installation, and running the setup assistant to configure Patcher for the first time.
- **Setup**: Detailed instructions for configuring Patcher to fit your organization's needs, including Jamf Pro integration and scheduling automated reports. 
- **Usage**: Explore how to use Patcher's commands and features, from exporting patch data and customizing reports to analyzing software titles and trends.
- **Support and Troubleshooting**: Get answers to common questions and find solutions to potential issues. 

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
installomator_support
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
