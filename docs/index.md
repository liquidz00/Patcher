---
layout: landing
description: "Simplified patch management reporting for macOS fleets on Jamf Pro. Open-source Python CLI and library; PDF, HTML, Excel, and JSON exports."
---

# Patcher

![](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)
![](https://img.shields.io/github/v/release/liquidz00/Patcher?logo=github&logoColor=white&color=orange)
![](https://img.shields.io/github/actions/workflow/status/liquidz00/Patcher/pytest.yml?logo=github&logoColor=white&label=Run+Tests)
![](https://img.shields.io/pypi/v/patcherctl?logo=pypi&logoColor=white&color=yellow)
![](https://img.shields.io/badge/macOS-13%2B-blueviolet?logo=apple&logoColor=white&logoSize=auto)

:::{rst-class} lead
A Python package and CLI for **patch analysis and reporting** on macOS fleets managed by [Jamf Pro](https://jamf.com/products/jamf-pro/).
:::

---

:::{container} buttons
[Docs](getting-started/install.md)
[GitHub](https://github.com/liquidz00/Patcher)
:::

## Key Features

::::{grid} 1 2 3 3
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:graph-16` **Analysis**
:link: guides/usage/cli
:link-type: doc

Cross-reference Jamf Pro's patch-management view of your fleet against [Installomator](https://github.com/Installomator/Installomator), [Homebrew](https://github.com/Homebrew/brew), [AutoPkg](https://github.com/autopkg/autopkg), and [Jamf App Installers](https://learn.jamf.com/r/en-US/jamf-pro-documentation-current/App_Installers).
:::

:::{grid-item-card} {iconify}`octicon:checklist-16` **Reporting**
:link: guides/usage/cli
:link-type: doc

Export customizable reports into PDF, Excel, HTML and JSON formats tailored to a tracked Jamf Pro instance.
:::

:::{grid-item-card} {iconify}`octicon:plug-16` **Catalog API**
:link: reference/api/endpoints
:link-type: doc

A community-facing API stitching upstream application sources into a single queryable surface.
:::

:::{grid-item-card} {iconify}`octicon:terminal-16` **Library & CLI**
:link: guides/usage/index
:link-type: doc

Use as `patcherctl` or import as a Python library; same operations either way.
:::

:::{grid-item-card} {iconify}`octicon:workflow-16` **Unattended Runs**
:link: guides/automation
:link-type: doc

Set it and forget it; recipes for automating Patcher with `launchd` and GitHub Actions support.
:::

:::{grid-item-card} {iconify}`octicon:paintbrush-16` **Custom branding**
:link: getting-started/customization
:link-type: doc

PDF and HTML reports take your header text, footer, fonts, logo and accent color to bring reports to life.
:::
::::

## Quick Start

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`mdi:bash` CLI
:sync: cli

```bash
$ patcherctl export --path ./reports
```

First run launches the interactive setup wizard for your Jamf URL, API client ID, and secret. SSO instance? See {doc}`Setup </getting-started/setup>` for the manual API-client path.
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
import asyncio
from patcher import PatcherClient

async def main():
    async with PatcherClient(
        client_id="...",
        client_secret="...",
        server="https://yourorg.jamfcloud.com",
    ) as patcher:
        titles = await patcher.fetch_patches()
        await patcher.export(titles, output_dir="./reports", formats={"pdf"})

asyncio.run(main())
```

If you've already run setup on this Mac, swap to {meth}`PatcherClient.from_state() <patcher.core.patcher_client.PatcherClient.from_state>` to pick up existing configurations.
:::

::::

## Getting Help

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`devicon:slack` MacAdmins Slack
:link: https://macadmins.slack.com/archives/C07EH1R7LB0

Join the `#patcher` channel and say hi.
:::

:::{grid-item-card} {iconify}`mdi:github` GitHub Issues
:link: https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml

Report bugs or submit feedback and feature requests.

:::
::::

## License

Patcher is licensed under the Apache License 2.0. See the [LICENSE](https://github.com/liquidz00/Patcher/blob/main/LICENSE) file for details.

---

Built with 💙 for the MacAdmins community


```{toctree}
:caption: 🚀  Getting Started
:hidden:

getting-started/install
getting-started/jamf-api
getting-started/setup
getting-started/customization
```

```{toctree}
:caption: 🔎  Guides
:hidden:

guides/usage/index
guides/agents
guides/automation
guides/recipes
```

```{toctree}
:caption: 📦  Project
:hidden:

project/contributing
project/architecture/index
project/sources
project/data-storage
project/self-hosting
project/troubleshooting
```

```{toctree}
:caption: 📖  Reference
:hidden:

reference/library/index
reference/api/index
reference/mcp/index
reference/models/index
reference/building-blocks/index
reference/helpers/index
reference/internals/index
```
