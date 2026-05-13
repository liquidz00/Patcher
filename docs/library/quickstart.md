(library-quickstart)=

# Library Quickstart

Patcher can be used as a Python library — every CLI feature is built on top of the same public classes you call directly. This page walks through the minimum to get from `pip install` to your first authenticated Jamf API call.

## Install

```console
$ python3 -m pip install --upgrade patcherctl
```

Same package as the CLI. The `patcherctl` command and the importable `patcher` package ship together; there is no separate library-only distribution.

:::{tip}
You do not need to run `patcherctl setup` to use Patcher as a library. Setup is only for the CLI — it stores credentials in the macOS keychain so subsequent CLI invocations don't have to prompt. Library callers pass credentials directly to {class}`~patcher.PatcherClient`.
:::

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
        policies = await patcher.jamf.get_policies()
        summaries = await patcher.jamf.get_summaries(policies)
        print(f"Found {len(summaries)} patch titles")


asyncio.run(main())
```

That's the whole library API for a basic summary fetch. A few things worth knowing:

- **Async context manager preferred.** `async with PatcherClient(...) as patcher:` guarantees the underlying httpx connection pool is released on exit. If you can't use `async with` (e.g., FastAPI startup hooks), construct directly and call `await patcher.aclose()` when done.
- **In-memory credentials.** Nothing is written to disk, no keyring backend required. Credentials live on the {class}`~patcher.core.config_manager.ConfigManager` for the lifetime of the `PatcherClient` instance.
- **Sensible default concurrency.** Defaults to 5 concurrent Jamf API requests — the recommended ceiling per Jamf's [scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices). Override with `concurrency=`.
- **Returns Pydantic models.** {class}`~patcher.PatchTitle` and {class}`~patcher.PatchDevice` are the return shapes for the report-shaped methods. Import them from `patcher` if you want to type-annotate your own code.

## What's next

- {ref}`Common patterns <library-recipes>` — using individual clients standalone, exporting reports, Installomator label matching, custom concurrency, and more.
- {doc}`API reference <../reference/index>` — full method signatures for every public class.
