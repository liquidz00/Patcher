# Patcher

_Patch reporting simplified_

![](https://img.shields.io/badge/license-apache_2.0-blue)&nbsp;![](https://img.shields.io/badge/python-3.9%2B-success)&nbsp;![](https://github.com/liquidz00/patcher/actions/workflows/test.yaml/badge.svg)


Patcher leverages the Jamf Pro API to fetch patch management data and generate comprehensive reports in both Excel and PDF formats. It simplifies tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

## Features

- Fetches patch management data from a specified Jamf Pro instance.
- Generates reports in Excel format for detailed analysis.
- Creates PDF reports for easy sharing and presentation.
- Customizable report headers and footers through a simple configuration.

## Getting Started

### Prerequisites

- Python 3.9 or higher.
- Access to a Jamf Pro instance with API credentials.

> **Note**<br>
> Although not required, it is **highly recommended** to create an API client for use with Patcher. For more details, reference the [Jamf Pro Documentation](https://learn.jamf.com/bundle/jamf-pro-documentation-current/page/API_Roles_and_Clients.html) on API Roles and Clients.

### Installation

1. **Clone the Repository**
```shell
git clone https://github.com/liquidz00/patcher.git
cd patcher
```
2. **Run the Installer Script**
The installer script will guide you through setting up your Jamf Pro instance details and installing project dependencies.
```shell
chmod +x installer.sh
./installer.sh
```
Follow the prompts to enter your Jamf Pro URL, Client ID, Client Secret, and Token. You'll also be asked to customize the report header and footer text. Optionally, you can opt to use a custom font instead of the default font [Assistant](https://fonts.google.com/specimen/Assistant).

### Usage
After installation, you can generate reports by running the main script. You can specify the output directory for the reports and choose to generate PDF reports alongside Excel files.
```shell
python patcher.py --path /path/to/output/directory [--pdf]
```
- The `--path` option specifies the directory where the reports will be saved.
- The optional `--pdf` flag indicates if PDF reports should be generated in addition to Excel files.

### Customizing Report UI
To customize the UI elements like header and footer text after the initial setup, edit the `ui_config.py` file in the project directory. Changes will be reflected in subsequent reports.

## Contributing
Contributions to Patcher are welcome! Please feel free to submit pull requests or create issues for bugs, questions, or new feature requests.

## License
This project is licensed under the Apache 2.0 License. See LICENSE.txt for details.




