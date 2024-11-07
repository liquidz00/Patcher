# Installation

Once prerequisites have been satisfied, Patcher can be installed via `pip`:

```console
$ python3 -m pip install --upgrade patcherctl
```
:::
### Installing Beta Releases from TestPyPI
:::
Patcher beta releases are published to [Test PyPI](https://test.pypi.org/project/patcherctl/). To install a beta version, you must specify the TestPyPI index:

```console
$ python3 -m pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple patcherctl=={VERSION}
```

Replace `{VERSION}` with the specific beta version number, such as `1.3.4b2`.

:::{note}
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

Usage: patcherctl [OPTIONS]

Options:
  --version                       Show the version and exit.
  -p, --path PATH                 Path to save the report(s)
  -f, --pdf                       Generate a PDF report along with Excel
                                  spreadsheet
  -s, --sort TEXT                 Sort patch reports by a specified column.
  -o, --omit                      Omit software titles with patches released
                                  in last 48 hours
  -d, --date-format [Month-Year|Month-Day-Year|Year-Month-Day|Day-Month-Year|Full]
                                  Specify the date format for the PDF header
                                  from predefined choices.
  -m, --ios                       Include the amount of enrolled mobile
                                  devices on the latest version of their
                                  respective OS.
  --concurrency INTEGER           Set the maximum concurrency level for API
                                  calls.
  -x, --debug                     Enable debug logging to see detailed debug
                                  messages.
  -r, --reset                     Resets the setup process and triggers the
                                  setup assistant again.
  --help                          Show this message and exit.
```

(ssl-verify)=
## SSL Verification

As of version 1.4.1, Patcher no longer modifies SSL configurations. SSL handling for custom certificates required some additional TLC by end users and would often cause SSL verification errors at runtime. This is compounded when taking into account our end users are likely on managed systems with security policies and third-party certificates (e.g., Zscaler).  

With the current version, SSL handling is no longer required by the end user. We've integrated ``curl`` with ``asyncio`` within Patcher's functionality to automatically handle SSL verification as part of API requests. This design choice removes the need for manual SSL configurations, streamlining the setup for MacAdmins on managed computers. 

:::{note}
While the current integration between `curl` and `asyncio` gets the job done for handling SSL verification, there's room for refinement. Community contributions to enhance this functionality are welcome and encouraged. If you're interested in exploring ways to solidify this process further, check out the relevant code in the {ref}`BaseAPIClient <base_api_client>` class.
:::

This update makes it easier for Patcher to run smoothly in secure environments, without the hassle of adjusting system certificates or tinkering with Python’s SSL settings.

**If none of the above steps worked to resolve the issue**, please reach out to us and let us know what (if any) security software is installed on your machine. This will help us troubleshoot issues in the future. Additionally, get in touch with someone from your security team for next steps as they may have a solution in place. 
