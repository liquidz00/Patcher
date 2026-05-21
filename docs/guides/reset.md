---
description: "Reset Patcher's persisted state: credentials, UI configuration, cache, or all of it. Covers the patcherctl reset command and PatcherClient.reset."
---

(reset)=
(resetting_patcher)=

# Resetting Configuration

:::{rst-class} lead
Controlling Patcher's state granularly.
:::

---

The `reset` command restores specific configurations in Patcher. By default a **full reset** clears everything and re-runs the setup wizard. You can also reset individual components (credentials, UI settings, or cached data) without touching the rest.

:::{note}
Options are case-insensitive. `full`, `Full`, and `FULL` all work.
:::

## Options

| Option | What it resets |
|---|---|
| `full` | Credentials, UI config, setup state, and cache, then re-runs the setup wizard |
| `UI` | PDF report appearance (header / footer text, font, optional logo) |
| `creds` | Keychain credentials (URL, Client ID, Client Secret), all of them or just one |
| `cache` | Cached patch data under `~/Library/Caches/Patcher` |

:::{caution}
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

Or scope to a single credential by name (one of `url`, `client_id`, `client_secret`):

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

{meth}`PatcherClient.reset <patcher.core.patcher_client.PatcherClient.reset>` mirrors the CLI's four reset kinds. The library version doesn't re-launch the setup wizard after a `"full"` reset — re-construct a `PatcherClient` yourself once you've populated new credentials.

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

```console
$ patcherctl reset cache
$ patcherctl reset UI
$ patcherctl reset creds
$ patcherctl reset creds --credential url
$ patcherctl reset full
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
async with PatcherClient.from_state() as patcher:
    await patcher.reset("cache")
    await patcher.reset("UI")
    await patcher.reset("creds")
    await patcher.reset("creds", credential="url")
    await patcher.reset("full")
```

The `"creds"`, `"UI"`, and `"full"` kinds require keychain-backed credentials and raise {class}`~patcher.core.exceptions.PatcherError` when called on a client constructed with in-memory credentials.
:::

::::

:::{seealso}
For more about cached data and where Patcher stores it, see {doc}`/project/data-storage`.
:::
