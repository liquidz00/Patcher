# Patcher

_Patch reporting simplified_

![](https://img.shields.io/pypi/l/patcherctl)&nbsp;![](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)&nbsp;![](https://img.shields.io/github/v/release/liquidz00/Patcher?color=orange)&nbsp;![](https://github.com/liquidz00/patcher/actions/workflows/pytest.yml/badge.svg)&nbsp;![](https://img.shields.io/pypi/v/patcherctl?color=yellow)


Patcher leverages the Jamf Pro API to fetch patch management data and generate comprehensive reports in both Excel and PDF formats. It simplifies tracking and reporting on software update compliance across macOS devices managed through Jamf Pro.

## Documentation
Project documentation can now be found [on our project homepage](https://patcher.liquidzoo.io). All content from our project wiki has been migrated to the new homepage. We are continuously updating references to the new homepage and regularly improving the documentation. 

### Sample PDF
Assuming 'AnyOrg' is the name of your organization, an exported PDF could look like this:
<p align="left"><img src="docs/_static/example_pdf.png" width="750"/></p>

### Installation
Install via `pip`:

```shell
pip install patcherctl
```
> [!NOTE]
> Please note that while Patcher is installed as a package, it is meant to be used as a command line tool and not as an imported library.

*Why `patcherctl?` The pip package is called patcherctl because the name patcher was already taken on PyPI. Despite this, the project itself is referred to as Patcher*

### Usage
After installation, you can generate reports by running the main script. You can specify the output directory for the reports and choose to generate PDF reports alongside Excel files.
```shell
patcherctl --path '/path/to/output/directory' [--pdf]
```

For a list of all available command options, visit the [usage page](https://patcher.liquidzoo.io/user/usage.html) of our documentation. 

## Authors & Contributions
Patcher is co-authored by [Andrew Speciale - @liquidz00](https://github.com/liquidz00) and [Chris Ball - @ball42](https://github.com/ball42). [Contributions](https://patcher.liquidzoo.io/contributing/index.html) to Patcher are welcome! We have set up templates for submitting issues, feature requests, and feedback. Please be sure to utilize these templates when contributing to the project.
