---
html_theme.sidebar_secondary.remove: True
---

(support)=

# Troubleshooting

For a list of Patcher exit codes and viewing help, visit the {ref}`usage <exit-codes>` page. 

## Debugging

By default, logs written to Patcher's log file are INFO and higher. Running the same command with the ``--debug`` flag will show all levels of logs to ``stdout`` *and* the log file.

```{code-block} bash
$ patcherctl <command> <options> --debug
```

(logs)=

## Interpreting Patcher Logs

Patcher's log(s) are stored in the Application Support directory of the user library: ``~/Library/Application Support/Patcher/logs``. There are three potential log files depending on configuration:

1. **``patcher.log``**: The primary log file used when any Patcher command is invoked.
2. **``patcher-agent.out.log``**: Standard out (``stdout``) log used by the {ref}`LaunchAgent <launch_agent>`. 
3. **``patcher-agent.err.log``**: Errors (``stderr``) logged by the {ref}`LaunchAgent <launch_agent>`.

Each log entry contains a timestamp, the {ref}`child logger <child-logger>` writing the log, and log level. 

### Sample log

:::{card} Sample error
:class-card: sd-card

```{code-block} text
2024-12-30 21:19:35,423 - Patcher.ApiClient - ERROR - Client error (401): [{'code': 'INVALID_TOKEN', 'description': 'Unauthorized', 'id': '0', 'field': None}]
```

The child logger in this case was the {class}`~patcher.client.api_client.ApiClient` class. This is helpful information to include in bug reports/issues. 
:::

:::{card} Debug & Info
:class-card: sd-card

```{code-block} text
2025-01-01 16:35:31,697 - Patcher.Analyzer - DEBUG - Attempting to filter titles by FilterCriteria.OLDEST_LEAST_COMPLETE.
2025-01-01 16:35:31,704 - Patcher.Analyzer - INFO - Filtered 5 PatchTitles successfully based on FilterCriteria.OLDEST_LEAST_COMPLETE
```
:::

## Potential Solutions

When encountering an issue, it is beneficial to separate environment issues (API credentials, network timeouts, etc.) versus configuration issues with Patcher (bug, property list issue, etc.). 

### Update Patcher

Ensure you are running the latest version of Patcher before proceeding. This is the least invasive and most straightforward method of resolving issues relating to Patcher: 

```{code-block} console
$ python3 -m pip install --upgrade patcherctl
```

### Full Reset

To rule out *configuration* issues with Patcher, perform a {ref}`full reset <full_reset>`. This will automatically trigger the setup process to run. If the issue persists after performing a full reset, proceed to reinstall Patcher.

:::{admonition} Known Issue
:class: danger

During the setup process, if an API Role or Client already exists for Patcher, the Jamf API will return a ``401`` response. It is recommended to retrieve the API credentials from keychain *before* performing the full reset, and proceeding with the {ref}`SSO setup type <setup_type>`. Alternatively, the API client and role can be removed from Jamf before performing the full reset if the standard setup type is preferred.
:::

### Reinstalling Patcher

As Patcher is distributed via PyPI, ``pip`` can be leveraged to uninstall and reinstall Patcher: 

```{code-block} console
$ python3 -m pip uninstall patcherctl
```

A prompt will show asking for confirmation to proceed. Enter ``Y`` to confirm uninstallation. 

```{code-block} console
Found existing installation: patcherctl <version>
Uninstalling patcherctl-<version>:
  Would remove:
    /Library/Frameworks/Python.framework/Versions/3.12/bin/patcherctl
    /Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/patcher/*
    /Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/patcherctl-<version>.dist-info/*
Proceed (Y/n)? 
```

:::{admonition} Optional
:class: admonition-optional

Before reinstalling Patcher, remove all contents from Patcher's Application Support directory **except** the ``logs`` directory. The logs should be kept to assist in troubleshooting the issue(s). The directory can be found at the following path: ``~/Library/Application Support/Patcher/``.
:::

Reinstall Patcher with ``python3 -m pip install patcherctl``. For detailed instructions, see {ref}`our install page <install>`. 

## Resources

If you're still running into issues with Patcher, there are a couple of ways to get in touch. 

### 1. Submit an Issue

Submitting an [issue](https://github.com/liquidz00/Patcher/issues/new/choose) on our GitHub repository is likely the quickest way to get support. Include as many details as possible, including what troubleshooting steps have already been taken to resolve the problem. Be sure to fill out as many fields on the issue form as able. We will do our best to get to the issue as quickly as we are able to.  

### 2. Reach out on the MacAdmins Slack

Despite having full-time jobs, we try to stay as active as possible on the MacAdmins Slack. Find us in the ``#patcher`` channel by clicking the banner at the top of the page. For other details on how to contribute, see {ref}`our contributing page <contributing_index>`. 

