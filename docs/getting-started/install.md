(install)=

# Installation

:::{rst-class} lead
Getting Patcher onto your Mac in a single command.
:::

Patcher ships as a single PyPI package (`patcherctl`) that exposes both the `patcherctl` CLI and the importable `patcher` Python library. One install gives you both surfaces; pick whichever fits your workflow.

## Prerequisites

- macOS (tested on 13+)
- Python 3.11 or newer
- A Jamf Pro instance with API access. See {doc}`jamf-api` to create the API role and OAuth client Patcher needs.

## Install

:::::{tab-set}

::::{tab-item} {iconify}`material-icon-theme:uv` uv
:sync: uv

```bash
uv pip install patcherctl
```

::::

::::{tab-item} {iconify}`devicon:pypi` pip
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

## Nuances and Gotchas

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
