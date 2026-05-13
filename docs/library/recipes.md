(library-recipes)=

# Common Patterns

Concrete examples for the most common library use cases beyond the basic quickstart. Each recipe is self-contained — copy, swap in your credentials, run.

## Skip `PatcherClient`: use `JamfClient` directly

If you only need the Jamf API and don't care about Installomator label matching or report export, instantiate {class}`~patcher.JamfClient` directly:

```python
import asyncio
from patcher import JamfClient


async def main():
    client = JamfClient.from_credentials(
        client_id="...",
        client_secret="...",
        server="https://yourorg.jamfcloud.com",
    )
    try:
        ids = await client.get_device_ids()
        versions = await client.get_device_os_versions(ids)
        print(f"Found {len(versions)} device OS versions")
    finally:
        await client.aclose()
```

{meth}`JamfClient.from_credentials <patcher.JamfClient.from_credentials>` wraps the credentials in an in-memory {class}`~patcher.core.config_manager.ConfigManager` — no keyring backend, no disk I/O.

## Installomator labels without Jamf credentials

{class}`~patcher.InstallomatorClient` is dual-mode. Construct it bare to fetch and parse [Installomator](https://github.com/Installomator/Installomator) labels without any Jamf credentials:

```python
import asyncio
from patcher import InstallomatorClient


async def main():
    iom = InstallomatorClient()
    labels = await iom.get_labels()
    print(f"Loaded {len(labels)} Installomator labels")

    firefox = await iom.get_label("firefox")
    print(firefox.expected_team_id, firefox.download_url)


asyncio.run(main())
```

This path uses an internal {class}`~patcher.client.HTTPClient` (generic httpx + truststore) — no Jamf authentication is performed.

## Installomator `match()` against Jamf titles

The `match()` algorithm correlates Jamf-configured software titles against Installomator labels, so it requires a configured {class}`~patcher.JamfClient`:

```python
import asyncio
from patcher import JamfClient, InstallomatorClient


async def main():
    jamf = JamfClient.from_credentials(
        client_id="...",
        client_secret="...",
        server="https://yourorg.jamfcloud.com",
    )
    iom = InstallomatorClient(api=jamf)

    try:
        titles = await jamf.get_summaries(await jamf.get_policies())
        await iom.match(titles)
        for t in titles:
            print(t.title, "->", t.install_label)
    finally:
        await jamf.aclose()
```

Calling `match()` on a bare `InstallomatorClient()` (no `api=`) raises a clear {class}`~patcher.PatcherError`.

## Export a report to disk

The {class}`~patcher.core.data_manager.DataManager` attached to a `PatcherClient` handles export to PDF, Excel, HTML, and JSON:

```python
import asyncio
from pathlib import Path

from patcher import PatcherClient


async def main():
    async with PatcherClient(
        client_id="...",
        client_secret="...",
        server="https://yourorg.jamfcloud.com",
    ) as patcher:
        summaries = await patcher.jamf.get_summaries(
            await patcher.jamf.get_policies()
        )
        await patcher.data.export(
            patch_titles=summaries,
            output_dir=Path("~/reports").expanduser(),
            report_title="Patch Report",
            formats={"pdf", "json"},
        )


asyncio.run(main())
```

Defaults to all four formats if `formats=` is omitted. See {class}`~patcher.core.data_manager.DataManager.export` for the full parameter list (date format, header color, per-title device sheets).

## Tune concurrency

Raise or lower the per-client concurrency ceiling — useful for very large Jamf instances where the 5-request default leaves throughput on the table, or for smaller instances where you want to be a more polite neighbor:

```python
async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
    concurrency=10,
) as patcher:
    ...
```

Anything above ~10 risks rate-limiting; check Jamf's [scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices) before pushing higher.

## Disable Installomator entirely

If you don't need Installomator label matching at all, pass `enable_installomator=False`. The `installomator` attribute becomes `None` and the GitHub label fetch is skipped:

```python
async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
    enable_installomator=False,
) as patcher:
    assert patcher.installomator is None
    summaries = await patcher.jamf.get_summaries(
        await patcher.jamf.get_policies()
    )
```

## Disable on-disk caching

By default, {class}`~patcher.core.data_manager.DataManager` caches fetched patch data to `~/Library/Application Support/Patcher/`. Disable that for stateless / CI-style runs:

```python
async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
    disable_cache=True,
) as patcher:
    ...
```
