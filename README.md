# Patcher

_Patch reporting simplified_

![](https://img.shields.io/badge/license-apache_2.0-blue)&nbsp;![](https://img.shields.io/badge/python-3.10%2B-blue)&nbsp;![](https://img.shields.io/github/v/release/liquidz00/Patcher?color=purple)&nbsp;![](https://github.com/liquidz00/patcher/actions/workflows/pytest.yml/badge.svg)


Patcher leverages the Jamf Pro API to fetch patch management data and generate comprehensive reports in both Excel and PDF formats. It simplifies tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

## Features

- Fetches patch management data from a specified Jamf Pro instance.
- Generates reports in Excel format for detailed analysis.
- Creates PDF reports for easy sharing and presentation.
- Customizable report headers and footers through a simple configuration.

### Sample PDF
The following image can be found in the `images` directory.
<p align="left"><img src="https://raw.githubusercontent.com/liquidz00/Patcher/develop/images/example_pdf.jpeg" width="750"/></p>

## Getting Started

### Prerequisites

> [!IMPORTANT]
> Patcher **requires** an API client for authentication. For instructions on creating an API Role & Client in Jamf Pro, refer to the [Jamf Pro Deployment Guide](https://github.com/liquidz00/Patcher/wiki/Jamf-Pro-Deployment-Guide#creating-an-api-role--client) in the wiki.

- Python 3.10+ (with pip).
- Git installed (via Homebrew or Developer Tools)
- Access to a Jamf Pro instance with administrator privileges (for API client creation).
- A Jamf Pro API Client with the following:
  - Read Patch Management Software Titles, Read Patch Policies, Read Mobile Devices, Read Mobile Device Inventory Collection, Read Mobile Device Applications, Read API Integrations, Read API Roles, and Read Patch Management Settings
  - Client ID
  - Client Secret

### Installation

> [!NOTE]
> Patcher can now be conveniently installed via `pip`. Please note that while Patcher is installed as a package, it is meant to be used as a command line tool and not as an imported library.

> [!TIP]
> **About the package name**: The pip package is called `patcherctl` because the name `patcher` was already taken on PyPI. Despite this, the project itself is referred to as Patcher.

**Run the Installer**
```shell
pip install patcherctl
```

### Usage
After installation, you can generate reports by running the main script. You can specify the output directory for the reports and choose to generate PDF reports alongside Excel files.
```shell
patcherctl --path '/path/to/output/directory' [--pdf]
```
- The `--path` option specifies the directory where the reports will be saved.
- The optional `--pdf` flag indicates if PDF reports should be generated in addition to Excel files.

For additional command options to use, visit the [Command Options](https://github.com/liquidz00/patcher/wiki/Command-Options) in the Wiki.

### Upcoming Features
We are developing functionality to have Patcher automatically create the necessary API Client and API Roles to simplify the prerequisites needed before use. Any assistance and contributions in this area would be greatly welcomed!

## Authors & Contributions
Patcher is co-authored by [Andrew Speciale - @liquidz00](https://github.com/liquidz00) and [Chris Ball - @ball42](https://github.com/ball42). Contributions to Patcher are welcome! We have set up templates for submitting issues, feature requests, and feedback. Please be sure to utilize these templates when contributing to the project.
