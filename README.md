# Patcher

_Patch reporting simplified_

![](https://img.shields.io/badge/license-apache_2.0-blue)&nbsp;![](https://img.shields.io/badge/python-3.9%2B-blue)&nbsp;![](https://img.shields.io/github/v/release/liquidz00/Patcher?color=purple)&nbsp;![](https://github.com/liquidz00/patcher/actions/workflows/pytest.yml/badge.svg)


Patcher leverages the Jamf Pro API to fetch patch management data and generate comprehensive reports in both Excel and PDF formats. It simplifies tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

## Features

- Fetches patch management data from a specified Jamf Pro instance.
- Generates reports in Excel format for detailed analysis.
- Creates PDF reports for easy sharing and presentation.
- Customizable report headers and footers through a simple configuration.

## Getting Started

### Prerequisites

> [!NOTE]
> Patcher **requires** an API client for authentication. For instructions on creating an API Role & Client in Jamf Pro, refer to the [Jamf Pro Deployment Guide](https://github.com/liquidz00/Patcher/wiki/Jamf-Pro-Deployment-Guide#creating-an-api-role--client) in the wiki.

- Python 3.9+ (with pip).
- Git installed (via Homebrew or Developer Tools)
- Access to a Jamf Pro instance with administrator privileges (for API client creation).
- A Jamf Pro API Client with the following:
  - Read Computers, Read Patch Reporting roles
  - Client ID
  - Client Secret
  - Bearer Token (Optional, installer script can generate one for you)

### Installation

1. **Run the Installer**
```shell
bash -c "$(curl -fsSL https://raw.githubusercontent.com/liquidz00/Patcher/main/tools/installer.sh)"
```
2. **Follow the Installer Script Prompts**
The installer script will guide you through setting up your Jamf Pro instance details and installing project dependencies. Follow the prompts to enter your Jamf Pro URL, Client ID, and Client Secret. If you already have a Bearer Token, you can pass the value to the installer script, otherwise the installer script will generate one for you. You'll also be asked to customize the report header and footer text. Optionally, you can opt to use a custom font instead of the default font [Assistant](https://fonts.google.com/specimen/Assistant).

### Usage
After installation, you can generate reports by running the main script. You can specify the output directory for the reports and choose to generate PDF reports alongside Excel files.
```shell
python3 patcher.py --path /path/to/output/directory [--pdf]
```
- The `--path` option specifies the directory where the reports will be saved.
- The optional `--pdf` flag indicates if PDF reports should be generated in addition to Excel files.

For additional command options to use, visit the [Command Options](https://github.com/liquidz00/patcher/wiki/Command-Options) in the Wiki.

### Customizing Report UI
To customize the UI elements like header and footer text after the initial setup, edit the `ui_config.py` file in the project directory. Changes will be reflected in subsequent reports.

## Authors & Contributions
Patcher is co-authored by [Andrew Speciale - @liquidz00](https://github.com/liquidz00) and [Chris Ball - @ball42](https://github.com/ball42). Contributions to Patcher are welcome! Please feel free to submit pull requests or create issues for bugs, questions, or new feature requests.
