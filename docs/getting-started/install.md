---
description: "Install Patcher on macOS via PyPI with uv or pip. Covers PATH gotchas, SSL/corporate-proxy support, and macOS 13+ requirements."
---

(install)=

# Installation

:::{rst-class} lead
Getting Patcher onto your Mac in a single command.
:::

---

Patcher ships as a single PyPI package (`patcherctl`) that includes both the CLI and the importable `patcher` Python library. Pick whichever one fits your workflow.

## Prerequisites

::::{highlights}
{iconify}`material-icon-theme:applescript` macOS (13+)
: Patcher is macOS-only, sorry Windows users!

{iconify}`material-icon-theme:python` Python 3.11+
: From [Python.org](https://www.python.org/downloads/release/python-31115/) or install and use [uv](https://docs.astral.sh/uv/)

{iconify}`material-icon-theme:key` Jamf Pro Access
: For OAuth client credential creation and patch title management
::::

## Install

:::::{tab-set}

::::{tab-item} {iconify}`material-icon-theme:uv` uv
:sync: uv

```bash
$ uv pip install patcherctl
```

::::

::::{tab-item} {iconify}`material-icon-theme:python` pip
:sync: pip

```bash
python3 -m pip install patcherctl
```

::::
:::::

## Nuances

Quirks that may arise during installation or usage of Patcher.

(add-path)=

### Adding to environment path

If `patcherctl --version` returns `command not found`, your Python user-base `bin` directory isn't on your `PATH`. To add it permanently, execute the following command in Terminal:

```bash
$ echo 'export PATH=$(python3 -m site --user-base)/bin:$PATH' >> ~/.zshrc && source ~/.zshrc
```

Adjust the profile path for your shell if you're not using `zsh` (e.g. `~/.bashrc`).

(ssl-verify)=

### SSL verification

Patcher uses [`httpx`](https://www.python-httpx.org/) with [`truststore`](https://github.com/sethmlarson/truststore) to bridge TLS verification to your macOS Keychain. Any CA your MDM installs at the OS level is automatically trusted (no Python-specific configuration required), and TLS-inspecting proxies (Zscaler, Netskope, Cloudflare Gateway, Palo Alto GlobalProtect) work transparently.

```{versionchanged} 2.5
The HTTP transport migrated from subprocess-`curl` to `httpx`. This is an internal change; `patcherctl` and `PatcherClient` behavior is unchanged for end users.
```

If you encounter certificate errors anyway, see {ref}`TLS / Corporate Proxies <support>` on the Troubleshooting page for diagnostic steps.
