(install)=

# Installation

Once prerequisites have been satisfied, Patcher can be installed via `pip`:

```console
$ python3 -m pip install --upgrade patcherctl
```

## Installing Beta Releases

Patcher beta releases are published to [Test PyPI](https://test.pypi.org/project/patcherctl/). To install a beta version, you must specify the TestPyPI index:

```console
$ python3 -m pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple patcherctl=={VERSION}
```

Replace `{VERSION}` with the specific beta version number, such as `1.3.4b2`.

:::{important}
Using the `--pre` option alone will not install beta releases from TestPyPI since it only applies to the main PyPI repository. You must explicitly specify the TestPyPI URL to access beta versions.
:::

## Verifying the Installation

After installation, you can verify Patcher is installed correctly by running:

```console
$ patcherctl --version
```

This should display the installed version of Patcher. Additionally, the `--help` command can also verify installation and show helpful {ref}`options to pass <usage>` at runtime:

```shell
$ patcherctl --help

Usage: python -m patcher.cli <options> COMMAND [ARGS]...

  Main CLI entry point for Patcher.

  Visit our project documentation for full details:
  https://patcher.readthedocs.io.

  Exit Codes:
      0   Success
      1   General error (e.g., PatcherError or user-facing issue)
      2   Unhandled exception
      4   API error (e.g., unauthorized, invalid response)
      130 KeyboardInterrupt (Ctrl+C)

Options:
  --version    Show the version and exit.
  -x, --debug  Enable debug logging (verbose mode).
  -h, --help   Show this message and exit.

Commands:
  analyze  Analyzes exported data by criteria.
  export   Exports patch management reports.
  reset    Resets configuration based on kind.
```

If instead you are presented with an error such as ``command not found``, ensure your ``PATH`` includes the appropriate directory. If you installed Python from python.org, the installer automatically added the Python framework to your PATH.

(add-path)=

### Adding Python to ``PATH``

CLI tools are typically installed to the ``/bin`` subdirectory of the Python framework. This can be added to your shell ``PATH`` by executing:

```{code-block} bash
echo 'export PATH=$(python3 -m site --user-base)/bin:$PATH' >> ~/.zshrc && source ~/.zshrc
```

If ``zsh`` is not your default shell, adjust the command to reflect the proper shell profile (e.g., ``bashrc``)

(ssl-verify)=
## SSL Verification

Patcher uses [``httpx``](https://www.python-httpx.org/) for HTTP requests, paired with [``truststore``](https://github.com/sethmlarson/truststore) to bridge TLS verification to your operating system's native trust store (macOS Keychain, Windows Certificate Store, Linux's ``/etc/ssl/certs/``). Any CA your MDM installs at the OS level is automatically trusted — no Python-specific configuration required.

This handles the most common reasons SSL verification fails for MacAdmins:

- TLS-inspecting proxies (Zscaler, Netskope, Cloudflare Gateway, Palo Alto GlobalProtect) that issue dynamically-rotated corporate CAs
- Internal Jamf Pro instances signed by a company root not present in the public CA bundle

You should **not** need to modify ``certifi``'s ``cacert.pem``, set ``SSL_CERT_FILE``, or otherwise tinker with Python's SSL settings. If your browser can reach your Jamf Pro instance without a TLS warning, Patcher can too.

For deeper diagnostics if SSL errors persist (the CA isn't installed at the OS level, MDM profile not fully applied, etc.), see the {ref}`TLS / Corporate Proxies <support>` section of the Troubleshooting page.

**If none of the above resolved the issue**, please reach out and let us know what (if any) security software is installed on the machine — it helps us improve diagnostics. Also loop in your security team; they may have a known workaround for the proxy in question.
