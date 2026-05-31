---
description: "Configure Jamf credentials for the patcherctl CLI with the interactive setup wizard. Covers first-run, SSO, re-running, and manual keychain seeding."
---

(setup)=

# Setup

:::{rst-class} lead
Configuring the settings that power Patcher.
:::

---

Set up your Jamf credentials once and the `patcherctl` CLI uses them on every run. The setup wizard writes them to the macOS keychain so you don't have to re-enter them.

:::{seealso}
Using Patcher as a library? You don't have to hardcode credentials. Run `patcherctl --fresh` once on the machine, then construct with {meth}`PatcherClient.from_state() <patcher.core.patcher_client.PatcherClient.from_state>` to pick up the keychain-backed credentials (and persisted UI config) automatically. See the {doc}`library guide </guides/usage/library>` for usage from there.
:::

After installing Patcher and creating your Jamf API role + client ({doc}`jamf-api`), launch the wizard with `--fresh`:

```bash
$ patcherctl --fresh
```

It walks you through credential entry, optional Installomator and UI configuration, and writes the result to your macOS keychain so subsequent runs don't have to re-prompt.

:::{note}
A bare `patcherctl` with no arguments prints the help screen; it does not start setup. The wizard also kicks in automatically the first time you invoke a command while setup is incomplete, but it finishes and exits without running that command, so re-run the command afterward. `patcherctl --fresh` is the reliable way to launch setup on demand.
:::

## How first-run detection works

Patcher stores its configuration state in a property list at `~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist`. When you run a `patcherctl` command, the wizard kicks in if:

- The file doesn't exist yet (truly first run), or
- The file exists but `setup_completed` is `False`.

Once setup completes successfully, `setup_completed` is set to `True` and the wizard is skipped from then on.

:::{warning}
Don't edit `setup_completed` by hand. If you need to start over, use `patcherctl reset full` or `patcherctl --fresh` (see [Re-running setup](#starting_fresh) below).
:::

(setup_type)=

## Choosing setup type

After a brief greeting, the wizard asks how you want to authenticate:

```bash
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

## Re-running setup

`--fresh` forces the wizard regardless of saved completion state:

```bash
$ patcherctl --fresh
```

Use this when you want a clean slate without nuking cached data (for testing, fixing a typo'd credential, or rotating an API client). To also wipe credentials and cached data, use `patcherctl reset full` instead (see {doc}`/guides/usage/cli`).

:::{note}
If a previous Standard setup attempt failed *after* creating the API role and client on the Jamf side, a second Standard run will fail with a `400` because those objects already exist. Either delete them manually in Jamf and retry, or switch to SSO setup to reuse the existing client credentials.
:::

## Storing credentials manually (advanced)

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
