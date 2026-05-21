<div align="center">
    <a href="https://docs.patcherctl.dev/">
        <picture>
            <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logo-dark.svg">
            <source media="(prefers-color-scheme: light)" srcset="docs/_static/logo-light.svg">
            <img src="docs/_static/logo-light.svg" width="540" alt="Patcher">
        </picture>
    </a>

![](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)
![](https://img.shields.io/github/v/release/liquidz00/Patcher?color=orange)
![](https://github.com/liquidz00/patcher/actions/workflows/pytest.yml/badge.svg)
![](https://img.shields.io/pypi/v/patcherctl?color=yellow)
![](https://img.shields.io/badge/macOS-10.13%2B-blueviolet?logo=apple&logoSize=auto)

<p align="center">
    <img src="https://cdn.worldvectorlogo.com/logos/slack-new-logo.svg" width="16" style="vertical-align: middle; margin-right: 5px;"/>
    Find us in the <code>#patcher</code> channel in the <a href="https://www.macadmins.org">MacAdmins Slack</a>
</p>
</div>

----
## What is Patcher?
Patcher is a Python library **and** CLI for macOS that leverages the Jamf Pro API to fetch patch management data and generate comprehensive reports in varying formats. It simplifies tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

Read the full project documentation [on our project homepage](https://docs.patcherctl.dev).

## Installation

### Using uv

```console
$ uv pip install patcherctl
```

Don't have [uv](https://docs.astral.sh/uv/) yet? Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh`.

### Using pip

```console
$ python3 -m pip install --upgrade patcherctl
```

See the [install docs](https://docs.patcherctl.dev/en/latest/getting-started/install.html) for PATH setup, SSL/corporate-proxy notes, and the bundled [Claude Code skill](https://docs.patcherctl.dev/en/latest/getting-started/claude-code.html).

## Sample PDF
Assuming 'AnyOrg' is the name of your organization, an exported PDF could look like this:
<p align="left"><img src="docs/_static/example_pdf.png" width="750"/></p>

PDF Reports can be customized to fit your organizations branding needs. See [Customization](https://docs.patcherctl.dev/en/latest/getting-started/customization.html) in the project docs.

## Usage

Full library and CLI references plus assembled recipes live in the [Guides section](https://docs.patcherctl.dev/en/latest/guides/export.html) of the docs. The two quick examples below cover the common case: fetch Jamf's patch-management view and export reports.

### Library

```python
import asyncio
from patcher import PatcherClient

async def main():
    async with PatcherClient.from_state() as patcher:
        titles = await patcher.fetch_patches()
        await patcher.export(titles, output_dir="./reports", formats={"pdf"})

asyncio.run(main())
```

`from_state()` reuses credentials saved by the CLI setup wizard. For headless / CI use, pass `client_id=`, `client_secret=`, and `server=` directly to `PatcherClient(...)` to skip the keychain. See [Setup](https://docs.patcherctl.dev/en/latest/getting-started/setup.html) for both flows.

### CLI

```console
$ patcherctl export --path './reports'
```

Run `patcherctl --help` for the full flag set, or see [Exporting Reports](https://docs.patcherctl.dev/en/latest/guides/export.html) for the per-format options and tuning.

## Patcher API

A separate workspace member at [`api/`](api/) powers [Patcher's API](https://api.patcherctl.dev/docs), a community catalog of macOS app patching metadata. The catalog stitches data from [Installomator](https://github.com/Installomator/Installomator), [Homebrew Cask](https://github.com/Homebrew/homebrew-cask), [AutoPkg](https://github.com/autopkg/autopkg), and more into a single queryable surface.

Read endpoints are public, there is no authentication required. Endpoint reference and `curl` + `PatcherAPIClient` examples are at [docs.patcherctl.dev](https://docs.patcherctl.dev/en/latest/reference/api/endpoints.html).

## Contributing

[Contributions](https://docs.patcherctl.dev/en/latest/project/contributing.html) to Patcher are welcome! We have set up templates for submitting [issues](https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml), [feature requests](https://github.com/liquidz00/Patcher/issues/new?template=feature_request.yml), and [feedback](https://github.com/liquidz00/Patcher/issues/new?template=feedback.yml). Please be sure to utilize these templates when contributing to the project.

<!--
Author: Andrew Lerman
Keywords: patcher patcherctl jamf jamfpro macos installomator autopkg homebrew patch patchmanagement apple
-->
