<div align="center">
    <a href="https://docs.patcherctl.dev/">
        <picture>
            <source media="(prefers-color-scheme: dark)" srcset="docs/_static/logo-dark.svg">
            <source media="(prefers-color-scheme: light)" srcset="docs/_static/logo-light.svg">
            <img src="docs/_static/logo-light.svg" width="540" alt="Patcher">
        </picture>
    </a>

![](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)
![](https://img.shields.io/github/actions/workflow/status/liquidz00/Patcher/pytest.yml?logo=github&logoColor=white&label=Run+Tests)
![](https://img.shields.io/pypi/v/patcherctl?logo=pypi&logoColor=white&color=yellow)
![](https://img.shields.io/badge/macOS-13%2B-blueviolet?logo=apple&logoColor=white&logoSize=auto)
![](https://img.shields.io/badge/dynamic/json?url=https://api.patcherctl.dev/stats&query=%24.total_apps&label=catalog&suffix=%20apps&color=1abc9c&style=flat&logo=sqlite&logoColor=white&cacheSeconds=3600)

<p align="center">
    A python library and CLI for Jamf patch reporting and analysis, backed by a community app catalog API.
</p>

<p align="center">
    <img src="https://cdn.worldvectorlogo.com/logos/slack-new-logo.svg" width="16" height="16"/>
    <a href="https://www.macadmins.org">MacAdmins Slack</a> (<code>#patcher</code>) →
    &nbsp;&nbsp;|&nbsp;&nbsp;
    📘 <a href="https://docs.patcherctl.dev/en/latest/index.html">Project Docs</a> →
</p>
</div>

----

<p align="center">
    <img src="docs/_static/example_pdf.png" width="750" alt="Sample Patcher PDF report"/>
    <br>
    <sub>An exported PDF report for "AnyOrg". See <a href="https://docs.patcherctl.dev/en/latest/getting-started/customization.html">Customization</a> in the project docs for more.</sub>
</p>

## Installation

```bash
$ python3 -m pip install patcherctl
```

## Usage

Full library and CLI references plus assembled recipes live in the [Guides section](https://docs.patcherctl.dev/en/latest/guides/usage/index.html) of the docs. The two quick examples below cover the common case of fetching Jamf's patch-management view and exporting reports.

### Library

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

### CLI

```bash
$ patcherctl \
    --client-id="..." \
    --client-secret="..." \
    --url="https://yourorg.jamfcloud.com" \
    export --path="./reports" --format=pdf
```

## Patcher API

Patcher's API is a community catalog of macOS app patching metadata stitched from [Installomator](https://github.com/Installomator/Installomator), [Homebrew Cask](https://github.com/Homebrew/homebrew-cask), [AutoPkg](https://github.com/autopkg/autopkg) (and more) into a single queryable surface.

API is public, no authentication is required. See [project docs](https://docs.patcherctl.dev/en/latest/reference/api/examples.html) for `curl` and `PatcherClient` examples.

> [!NOTE]
> On a corporate network that filters new or uncategorized domains, the catalog API may be blocked by a web gateway. See [Catalog API Blocked by Web Filtering](https://docs.patcherctl.dev/en/latest/project/troubleshooting.html#api-blocked) to confirm and resolve it.

## Contributing

[Contributions](https://docs.patcherctl.dev/en/latest/project/contributing.html) to Patcher are welcome! We have set up templates for submitting [issues](https://github.com/liquidz00/Patcher/issues/new?template=bug_report.yml), [feature requests](https://github.com/liquidz00/Patcher/issues/new?template=feature_request.yml), and [feedback](https://github.com/liquidz00/Patcher/issues/new?template=feedback.yml). Please be sure to utilize these templates when contributing to the project.

<!--
Author: Andrew Lerman
Keywords: patcher patcherctl jamf jamfpro macos installomator autopkg homebrew patch patchmanagement apple
-->
