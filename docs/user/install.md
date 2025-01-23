(install)=

# Installation

Once prerequisites have been satisfied, Patcher can be installed via `pip`:

```console
$ python3 -m pip install --upgrade patcherctl
```

## Installing Beta Releases from TestPyPI

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
  https://patcher.liquidzoo.io.

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

As of version 1.4.1, Patcher no longer modifies SSL configurations. SSL handling for custom certificates required some additional TLC by end users and would often cause SSL verification errors at runtime. This is compounded when taking into account our end users are likely on managed systems with security policies and third-party certificates (e.g., Zscaler).  

With the current version, SSL handling is no longer required by the end user. We've integrated ``curl`` with ``asyncio`` within Patcher's functionality to automatically handle SSL verification as part of API requests. This design choice removes the need for manual SSL configurations, streamlining the setup for MacAdmins on managed computers. 

:::{note}
While the current integration between `curl` and `asyncio` gets the job done for handling SSL verification, there's room for refinement. Community contributions to enhance this functionality are welcome and encouraged. If you're interested in exploring ways to solidify this process further, check out the relevant code in the {ref}`BaseAPIClient <base_api_client>` class.
:::

This update makes it easier for Patcher to run smoothly in secure environments, without the hassle of adjusting system certificates or tinkering with Python’s SSL settings.

**If none of the above steps worked to resolve the issue**, please reach out to us and let us know what (if any) security software is installed on your machine. This will help us troubleshoot issues in the future. Additionally, get in touch with someone from your security team for next steps as they may have a solution in place. 
