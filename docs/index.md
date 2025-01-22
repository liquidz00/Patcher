---
html_theme.sidebar_secondary.remove: True
---

```{image} _static/v2-patcher-banner-light.svg
:class: only-light patcher-banner
:align: center
```

```{image} _static/v2-patcher-banner-dark.svg
:class: only-dark patcher-banner
:align: center
```

# Welcome to Patcher's Documentation!

Patcher is crafted with the needs of Mac Admins in mind, offering a streamlined approach to the often complex and time-consuming task of patch management. By automating the extraction and formatting of patch data, Patcher not only saves time but also ensures accuracy and consistency in the management of software updates.

## Features

- **Real-Time Patch Information Export**: Quickly extract up-to-date patch data for analysis.
- **Excel Spreadsheet Integration**: Seamlessly export patch information into Excel for in-depth analysis and record-keeping.
- **PDF Reporting**: Generate neatly formatted PDFs for easy sharing and documentation of patch statuses.
- **Customization Options**: Tailor the tool to match your organizations branding scheme with custom fonts and logo support.
- **Analysis**: Quickly analyze Patch Reports to identify which software titles may need some extra TLC.

::::{grid} 1 1 1 3
:gutter: 2
:padding: 2 2 0 0
:class-container: sd-text-center

:::{grid-item-card} {fas}`user;sd-text-primary` User Guide
:class-card: sd-card
:class-title: patcher-title
:shadow: md
:columns: 12

Setting yourself up for success--ensuring prerequisites are satisfied, installation instructions, running through the setup assistant, customization options, and command options and examples.

+++

```{button-ref} user/index
:ref-type: myst
:click-parent:
:color: secondary
:expand:

User Guide
```

:::

:::{grid-item-card} {fas}`book;sd-text-primary` Reference
:class-card: sd-card
:class-title: patcher-title
:shadow: md
:columns: 6

Patcher's source-code documentation for reference.

+++

```{button-ref} reference/index
:ref-type: myst
:click-parent:
:color: secondary
:expand:

Reference Guide
```

:::

:::{grid-item-card} {fas}`hands-helping;sd-text-primary` Contributing
:class-card: sd-card
:class-title: patcher-title
:shadow: md
:columns: 6

Resources and guides for contributors.

+++

```{button-ref} contributing_index
:ref-type: ref
:click-parent:
:color: secondary
:expand:

Contributing Guide
```

:::
::::

```{toctree}
:maxdepth: 2
:hidden:

user/index
reference/index
contributing/index
macadmins/index
```
