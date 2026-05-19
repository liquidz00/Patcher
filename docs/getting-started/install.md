---
description: "Install Patcher on macOS via PyPI with uv or pip. Covers PATH gotchas, SSL/corporate-proxy support, and macOS 13+ requirements."
---

(install)=

# Installation

:::{rst-class} lead
Getting Patcher onto your Mac in a single command.
:::

Patcher ships as a single PyPI package (`patcherctl`) that exposes both the `patcherctl` CLI and the importable `patcher` Python library. One install gives you both surfaces; pick whichever fits your workflow.

:::{note}
Patcher reports and analyzes patch state. It does **not** deploy software or run installers. If you need a deployment tool, look at [Installomator](https://github.com/Installomator/Installomator), [AutoPkg](https://github.com/autopkg/autopkg), [App Auto-Patch](https://github.com/App-Auto-Patch/App-Auto-Patch), or other alternatives.
:::

A few practical clarifications that come up often:

- **Patcher runs on your admin workstation or CI runner, not on managed Macs.** Nothing gets installed on the devices being tracked.
- **It reads from Jamf Pro's existing patch-management view.** That data needs to be populated in Jamf first; Patcher is an analysis layer on top, not a replacement for the patch policies themselves.
- **It surfaces state, not actions.** Patcher tells you what's stale, what's missing, and what's automation-ready. Closing those gaps still happens through the deployment tools above.

## Prerequisites

::::{grid} 3
:gutter: 2
:padding: 0

:::{grid-item-card} {iconify}`lucide:search` macOS (tested on 13+)
:::

:::{grid-item-card} {iconify}`lucide:file-bar-chart` Python 3.11 or newer
:::

:::{grid-item-card} {iconify}`lucide:server` Jamf Pro Access
:::
::::

## Install

:::::{tab-set}

::::{tab-item} {iconify}`material-icon-theme:uv` uv
:sync: uv

```bash
uv pip install patcherctl
```

::::

::::{tab-item} {iconify}`material-icon-theme:pypi` pip
:sync: pip

```bash
python3 -m pip install --upgrade patcherctl
```

::::
:::::

Verify the install:

```console
$ patcherctl --version
```

## Nuances

Quirks that may arise during installation or usage of Patcher.

(add-path)=

### `command not found` Error

If `patcherctl --version` returns `command not found`, your Python user-base `bin` directory isn't on your `PATH`. To add it permanently, execute the following command in Terminal:

```bash
echo 'export PATH=$(python3 -m site --user-base)/bin:$PATH' >> ~/.zshrc && source ~/.zshrc
```

Adjust the profile path for your shell if you're not using `zsh` (e.g. `~/.bashrc`).

(ssl-verify)=

### SSL verification

Patcher uses [`httpx`](https://www.python-httpx.org/) with [`truststore`](https://github.com/sethmlarson/truststore) to bridge TLS verification to your operating system's native trust store (macOS Keychain). Any CA your MDM installs at the OS level is automatically trusted (no Python-specific configuration required), and TLS-inspecting proxies (Zscaler, Netskope, Cloudflare Gateway, Palo Alto GlobalProtect) work transparently.

```{versionchanged} 2.5
The HTTP transport migrated from subprocess-`curl` to `httpx`. This is an internal change; `patcherctl` and `PatcherClient` behavior is unchanged for end users.
```

If you encounter certificate errors anyway, see {ref}`TLS / Corporate Proxies <support>` on the Troubleshooting page for diagnostic steps.
