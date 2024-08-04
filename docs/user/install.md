# Installation

Once prerequisites have been satisfied, Patcher can be installed via `pip`:

```shell
$ python3 -m pip install --upgrade patcherctl
```
:::
### Installing Beta Releases from TestPyPI
:::
Patcher beta releases are published to [Test PyPI](https://test.pypi.org/project/patcherctl/). To install a beta version, you must specify the TestPyPI index:

```shell
$ python3 -m pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple patcherctl=={VERSION}
```

Replace `{VERSION}` with the specific beta version number, such as `1.3.4b2`.

:::{note}
Using the `--pre` option alone will not install beta releases from TestPyPI since it only applies to the main PyPI repository. You must explicitly specify the TestPyPI URL to access beta versions.
:::

## Verifying the Installation

After installation, you can verify Patcher is installed correctly by running: 

```shell
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

## SSL Verification and Self-Signed Certificates

When using Patcher, you may encounter SSL verification issues, particularly if your network environment uses self-signed certificates or custom Certificate Authorities (CAs). Patcher uses both the `aiohttp` and `urllib` libraries to make API calls.

:::{note}
:class: dropdown

We are actively working on introducing the ability to pass the path of the certificate(s) to Patcher to handle SSL verification. 
:::

### Configure macOS to Trust Custom Certificates

If you are on a managed host, chances are this has already been done for you as part of being enrolled with an MDM. However, it never hurts to verify. 

1. Open the Keychain application in `/Applications/Utilities/Keychain Access.app`
2. Click **System** on the left sidebar underneath *System Keychains*, and select the **Certificates** tab
3. Locate the Certificate in question and double-click to open it
4. Set the certificate to "Always Trust" under the Trust section

#### Export the Certificate (Optional)

Alternatively, you may need to export the certificate in `.pem` format. If so, export the certificate from Keychain by right-clicking and selecting **Export** from the dialog menu. Be sure to select the file format as `.pem` when exporting. 

### Adding Custom Certificates

Patcher uses both `aiohttp` and `urllib` to make API requests. Both libraries rely on Python's built-in `ssl` module to handle SSL certificates. On macOS, Python *typically* uses the system's SSL certificate store or the certificates bundled with Python itself. 

:::{attention}
The following steps will likely need local administrator privileges (`sudo`). 
:::

#### Identify the Certificate Path

First, determine where Python is currently looking for certificates. You can find this by using the `ssl` module in Python.

::::{tab-set}

:::{tab-item} Command Prompt
```shell
$ python3 -c "import ssl; print(ssl.get_default_verify_paths())"
```
:::

:::{tab-item} Python
```python
import ssl

# Print default SSL certificate paths
print(ssl.get_default_verify_paths())
```
:::

::::

The command will output paths where Python looks for certificates, usually pointing to a `cert.pem` file or similar. Be sure to notate the proper path before proceeding.

#### Add the Self-Signed Certificate

If not completed already, [export](#export-the-certificate-optional) the certificate to a file location of your choosing. The certificate can then be added to the default bundle with the following command: 

```shell
$ cat /path/to/exported/certificate.pem >> /path/to/default/certificate/location/cert.pem
```

If permission errors are thrown, attempt the command again with `sudo`. 

**If none of the above steps worked to resolve the issue**, please reach out to us and let us know what (if any) security software is installed on your machine. This will help us troubleshoot issues in the future. Additionally, get in touch with someone from your security team for next steps as they may have a solution in place. 
