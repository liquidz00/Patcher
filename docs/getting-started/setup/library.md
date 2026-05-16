(library-quickstart)=

# Create a `PatcherClient`

:::{rst-class} lead
Skip the wizard. Pass credentials straight to `PatcherClient` from your own code, scripts, or services.
:::

Library callers skip the setup wizard entirely. Credentials are passed in-memory to {class}`~patcher.PatcherClient` and never touch disk or the macOS keychain.

## Your first call

The headline class is {class}`~patcher.PatcherClient`. It composes the per-service clients ({class}`~patcher.JamfClient`, {class}`~patcher.InstallomatorClient`) and a {class}`~patcher.core.data_manager.DataManager` into a single object:

```python
import asyncio
from patcher import PatcherClient


async def main():
    async with PatcherClient(
        client_id="your-jamf-api-client-id",
        client_secret="your-jamf-api-client-secret",
        server="https://yourorg.jamfcloud.com",
    ) as patcher:
        titles = await patcher.fetch_patches()
        print(f"Found {len(titles)} patch titles")


asyncio.run(main())
```

A few things to know:

- **Async context manager preferred.** `async with PatcherClient(...) as patcher:` guarantees the underlying `httpx` connection pool is released on exit. If you can't use `async with` (e.g. FastAPI startup hooks), construct directly and call `await patcher.aclose()` when done.
- **In-memory credentials.** Nothing is written to disk. No keyring backend required.
- **Sensible default concurrency.** 5 concurrent Jamf API requests, the recommended ceiling per [Jamf's scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices). Override with `concurrency=`.
- **Returns Pydantic models.** {class}`~patcher.PatchTitle` and {class}`~patcher.PatchDevice` are the return shapes for the report-shaped methods. Import them from `patcher` if you want type-annotated code.

## Construction options

| Kwarg | Default | Purpose |
|---|---|---|
| `client_id`, `client_secret`, `server` | required | Jamf API credentials |
| `concurrency` | `5` | Max concurrent Jamf API requests |
| `enable_installomator` | `True` | Set to `False` to skip Installomator label matching entirely. `patcher.installomator` becomes `None`. |
| `disable_cache` | `False` | Disable on-disk caching under `~/Library/Application Support/Patcher/`. Useful for stateless / CI runs. |

```python
async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
    concurrency=10,
    enable_installomator=False,
    disable_cache=True,
) as patcher:
    ...
```

## Working with individual clients

If you only need a subset (Jamf without Installomator, or Installomator labels without Jamf credentials), instantiate the per-service clients directly.

### `JamfClient` standalone

```python
from patcher import JamfClient

client = JamfClient.from_credentials(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
)
try:
    ids = await client.get_device_ids()
    versions = await client.get_device_os_versions(ids)
finally:
    await client.aclose()
```

{meth}`JamfClient.from_credentials <patcher.JamfClient.from_credentials>` wraps credentials in an in-memory {class}`~patcher.core.config_manager.ConfigManager`. No keyring backend, no disk I/O.

### `InstallomatorClient` standalone

Fetch and parse Installomator labels without any Jamf credentials:

```python
from patcher import InstallomatorClient

iom = InstallomatorClient()
labels = await iom.get_labels()
firefox = await iom.get_label("firefox")
print(firefox.expected_team_id, firefox.download_url)
```

Calling `match()` on a bare `InstallomatorClient()` (no `api=` argument) raises a clear {class}`~patcher.PatcherError`. Matching requires a configured Jamf client.

## What's next

- {doc}`/usage/export`: fetch and export patch reports
- {doc}`/usage/analyze`: filter and trend cached data
- {doc}`/integrations/installomator`: how Patcher correlates Jamf titles with Installomator labels
- {doc}`/reference/index`: full method signatures for every public class
