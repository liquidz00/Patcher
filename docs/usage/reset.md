(reset)=
(resetting_patcher)=

# Reset configuration

:::{rst-class} lead
Wipe credentials, UI config, cached data, or everything at once. Granular control over Patcher's state.
:::

The `reset` command restores specific configurations in Patcher. By default a **full reset** clears everything and re-runs the setup wizard. You can also reset individual components (credentials, UI settings, or cached data) without touching the rest.

## Options

| Option | What it resets |
|---|---|
| `full` | Credentials, UI config, setup state, and cache, then re-runs the setup wizard |
| `UI` | PDF report appearance (header / footer text, font, optional logo) |
| `creds` | Keychain credentials (URL, Client ID, Client Secret), all of them or just one |
| `cache` | Cached patch data under `~/Library/Caches/Patcher` |

:::{note}
Options are case-insensitive. `full`, `Full`, and `FULL` all work.
:::

:::{important}
A full credential reset prompts for **all three** values (URL, Client ID, Client Secret). Only run it if you have access to the new credentials, particularly if your environment doesn't use SSO, or you originally relied on Patcher's automatic setup wizard.
:::

## Examples

::::{tab-set}

:::{tab-item} Full
:sync: full

```console
$ patcherctl reset full
```

Resets everything and re-runs the setup wizard.
:::

:::{tab-item} UI
:sync: ui

```console
$ patcherctl reset UI
```

Refreshes the appearance of generated reports (header / footer text or custom logos). Patcher will re-prompt for UI settings after the reset succeeds.
:::

:::{tab-item} Credentials
:sync: creds

Reset all three credentials:

```console
$ patcherctl reset creds
```

Or just one. Pass `--credential` with `url`, `client_id`, or `client_secret`:

```console
$ patcherctl reset creds --credential url
```
:::

:::{tab-item} Cache
:sync: cache

```console
$ patcherctl reset cache
```

Removes all cache files from the cache directory.
:::

::::

## From the library

Most `reset` operations are CLI conveniences. Library callers typically manage their own credentials and UI preferences, so there's no high-level `PatcherClient.reset()` method.

The one exception is the patch-data cache, which is exposed on the `data` collaborator:

```python
from patcher import PatcherClient

async with PatcherClient(client_id=..., client_secret=..., server=...) as patcher:
    patcher.data.reset_cache()
```

`reset_cache()` is synchronous and returns `True` if all cached files were removed successfully.

:::{seealso}
For more about cached data and where Patcher stores it, see {doc}`/concepts/data-storage`.
:::
