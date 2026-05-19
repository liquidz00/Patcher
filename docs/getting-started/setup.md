---
description: "Configure Jamf credentials for both patcherctl and the PatcherClient library. Covers the interactive wizard, SSO setup, and library-mode credentials."
---

(setup)=

# Setup

:::{rst-class} lead
Configure Patcher for your environment. The same credentials power both the CLI and the library; set them up once.
:::

Set up your Jamf credentials once and both `patcherctl` and `PatcherClient` use them. The CLI's setup wizard writes to the macOS keychain; library callers pass credentials in-memory and skip the keychain entirely.

:::::::{tab-set}
:sync-group: surface

::::::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

After installing Patcher and creating your Jamf API role + client, run `patcherctl` to launch the interactive setup wizard. It walks you through credential entry, optional Installomator and UI configuration, and writes the result to your macOS keychain so subsequent runs don't have to re-prompt.

```console
$ patcherctl
```

That's the whole entry point. The wizard runs automatically on first launch.

### How first-run detection works

Patcher stores its configuration state in a property list at `~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist`. The wizard runs when:

- The file doesn't exist yet (truly first run), or
- The file exists but `setup_completed` is `False`.

Once setup completes successfully, `setup_completed` is set to `True` and the wizard is skipped on subsequent invocations.

:::{warning}
Don't edit `setup_completed` by hand. If you need to start over, use `patcherctl reset full` or `patcherctl --fresh` (see [Re-running setup](#starting_fresh) below).
:::

(setup_type)=

### Choosing setup type

After a brief greeting, the wizard asks how you want to authenticate:

```console
Choose setup method (1: Standard setup, 2: SSO setup) [1]:
```

:::::{tab-set}

::::{tab-item} Standard
:sync: standard

Patcher will create the API role + client on your behalf using your Jamf admin credentials. You'll be prompted for username and password during setup, but **these aren't stored**. They're used once to obtain a basic token, create the API integration, then discarded.

Use Standard if your Jamf account **doesn't** use SSO.
::::

::::{tab-item} SSO
:sync: sso

The Jamf Pro API [doesn't support SSO auth](https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#authentication-and-authorization), so Patcher can't auto-create the role + client for you. Create them manually first ({doc}`jamf-api`), then paste the resulting Client ID and Client Secret into the wizard when prompted.

Use SSO if your Jamf account uses Single Sign-On.
::::

:::::

(starting_fresh)=

### Re-running setup

Pass `--fresh` to force the wizard regardless of saved completion state:

```console
$ patcherctl --fresh
```

Use this when you want a clean slate without nuking cached data (for testing, fixing a typo'd credential, or rotating an API client). To also wipe credentials and cached data, use `patcherctl reset full` instead (see {doc}`/usage/reset`).

:::{note}
If a previous Standard setup attempt failed *after* creating the API role and client on the Jamf side, a second Standard run will fail with a `400` because those objects already exist. Either delete them manually in Jamf and retry, or switch to SSO setup to reuse the existing client credentials.
:::

### Storing credentials manually (advanced)

Patcher uses the [`keyring`](https://pypi.org/project/keyring/) library to persist credentials in the macOS login keychain. The wizard does this for you, but if you'd rather seed credentials ahead of time (e.g. provisioning a workstation script-side), this snippet writes them directly:

```python
import keyring

keyring.set_password("Patcher", "URL", "https://yourorg.jamfcloud.com")
keyring.set_password("Patcher", "CLIENT_ID", "your-client-id")
keyring.set_password("Patcher", "CLIENT_SECRET", "your-client-secret")
```

After running the script, the entries appear under the **login** keychain in Keychain Access under the service name `Patcher`.

:::{tip}
You can skip generating a bearer token. Patcher handles obtaining and refreshing tokens automatically.
:::

::::::

::::::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

(library-quickstart)=

Library callers skip the setup wizard entirely. Credentials are passed in-memory to {class}`~patcher.PatcherClient` and never touch disk or the macOS keychain.

### Your first call

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

### Construction options

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

### Working with individual clients

If you only need a subset (Jamf without Installomator, or Installomator labels without Jamf credentials), instantiate the per-service clients directly.

#### `JamfClient` standalone

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

#### `InstallomatorClient` standalone

Fetch and parse Installomator labels without any Jamf credentials:

```python
from patcher import InstallomatorClient

iom = InstallomatorClient()
labels = await iom.get_labels()
firefox = await iom.get_label("firefox")
print(firefox.expected_team_id, firefox.download_url)
```

Calling `match()` on a bare `InstallomatorClient()` (no `api=` argument) raises a clear {class}`~patcher.PatcherError`. Matching requires a configured Jamf client.

### What's next

- {doc}`/usage/export`: fetch and export patch reports
- {doc}`/usage/analyze`: filter and trend cached data
- {doc}`/reference/index`: full method signatures for every public class

::::::

:::::::
