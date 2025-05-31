<!-- markdownlint-capture -->
<!-- markdownlint-disable -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.2.0] - 2025-05-31
### Added
- Setup assistant tracks completion progress to prevent redundancy and `400` errors ([#29](https://github.com/liquidz00/Patcher/issues/29))
- Setup can be forcibly restarted by passing the `--fresh` argument, regardless of previous completion

### Changed
- Greeting is only shown if setup is in initial state to prevent redundancy. ([Docs](https://patcher.liquidzoo.io/user/setup_assistant.html#resumable-setup:~:text=last%20successful%20step.-,The%20stages%20are%3A,-not_started%3A%20Initial%20stage))

## [v2.1.3] - 2025-03-16
### Changed
- Warnings about skipped Installomator labels are logged instead of being shown directly to stdout

### Fixed
- An issue causing the HTML template directory to not be included in built distribution

## [v2.1.2] - 2025-03-14
### Changed
- Problematic Installomator labels are now handled gracefully instead of raising exceptions ([#28](https://github.com/liquidz00/Patcher/issues/28))
- PDF classes have been refactored to resolve FPDF Deprecation warnings around `ln=True` usage

### Fixed
- An issue with HTML template path reference ([#27](https://github.com/liquidz00/Patcher/issues/27))
- CLI entry point references the correct property list value for HTML report titles

## [v2.1.1] - 2025-03-13
### Added
- Installomator support can be disabled should it not align with the security standards of your environment ([Docs](https://patcher.liquidzoo.io/user/installomator_support.html#disabling-installomator))

### Changed
- Property list structure has been reformatted for simplicity and efficiency. ([Docs](https://patcher.liquidzoo.io/user/plist.html))
- All property list methods refactored into own `PropertyListManager` class for separation of concerns

### Fixed
- An issue with bold fonts not be adding properly, leading to unhandled FPDF exceptions
- `404` status responses are properly handled during app matching process instead of raising an `APIResponseError` ([#26](https://github.com/liquidz00/Patcher/issues/26))
- Prevent inaccurate setup runs by checking property list migration before setup completion

## [v2.1.0] - 2025-02-15
### Added
- Export command defaults to exporting to all file formats (Excel, PDF, and HTML), with the `--format` option allowing for export of specific formats if desired
- [Installomator](https://github.com/Installomator/Installomator) matching. `PatchTitle` objects are matched with Installomator labels upon export
- Installomator `FilterCriteria` to show which labels are supported by Installomator

### Changed
- Added hour and minute information to cached data timestamp, allowing for caching of multiple reports in same day

### Fixed
- An issue where `date_format` was not being properly formatted as a datetime object in exported HTML reports
- `OSError` and `PermissionError` types are properly handled when trying to create directories
- `app_names` key returns a list of `appName` strings instead of first entry only
- An issue where `ReportManager` objects were not properly awaiting async functions

## [v2.0.3] - 2025-02-05
### Fixed
- Data sets are cached before dropping ignored columns so that analysis can complete as expected

## [v2.0.2] - 2025-02-02
### Added
- Support for tracking `softwareTitleId` from Jamf API Response
- macOS badge to README.md

### Changed
- Ignored columns are formatted properly before being dropped from export
- `title_id` attribute  is set to `"iOS"` when calculating amount of devices on latest version

### Fixed
- HTML template path references [#25](https://github.com/liquidz00/Patcher/issues/25)

## [v2.0.1] - 2025-01-24
### Fixed
- Resolved an issue where the entry point in `pyproject.toml` was not updated, preventing proper execution
- All changes from v2.0.0 are included in this release

## [v2.0.0] - 2025-01-23 [YANKED]
> **This release was yanked from PyPi due to an incorrect entry point configuration in the projects TOML file. This issue was fixed in v2.0.1.**

### Added
- Generated analyze summary file is now exported as an HTML report instead of a `.txt` file
- Title, header, and date format are dynamically set in HTML reports
- Support for data caching and resetting any cached data present
- `execute_sync` method to support synchronous API calls to prevent race conditions
- `Analyzer` class for analyzing collected patch management data based upon specified criteria
- Minimal viable product (MVP) class to begin [Installomator](https://github.com/Installomator/Installomator) support
- New export format support now leverages the `DataManager` class with automatic caching functionality

### Changed
- `ExcelReport` class refactored into `DataManager` class to support automatic caching
- `excel_file` parameter is no longer *required*, `DataManager` objects will default to latest cached dataset available
- `INFO`, `DEBUG`, and `WARNING` log level messages now have consistent format

### Deprecated
- `AccessToken` management has been refactored into `TokenManager`, deprecating `headers` property

### Fixed
- An issue where the default UI configuration was being overwritten mistakenly
- An issue with the `reset` method improperly returning `False` on successful resets
- An issue where stale `AccessToken` objects were being retrieved, leading to unauthorized API calls
- Refactored `None` to `""` when handling property lists to prevent `plistlib` errors

## [v1.4.1] - 2024-11-07
### Added
- `BaseAPIClient` class which allows for async `curl` calls as a workaround for SSL issues
- `SetupError` exception class to raise instead of returning `None`

### Changed
- `BaseAPIClient` class is utilized for API operations
- Max concurrency handling moved to `BaseAPIClient`
- Support both `GET` and `POST` requests in API calls
- API Role and API Client creation workflow leverages `fetch_json` method for improved HTTP error handling
- Credentials are lazy-loaded when needed instead of during init to prevent premature validation errors
- `ApiClient` and `TokenManager` objects are instantiated after completion of `Setup`
- Scope of `Setup` class has been narrowed, moving out-of-scope methods to proper classes

### Removed
- `APIPrivilegeError` exception

### Fixed
- Default header handling in API requests
- Calls for setting concurrency level
- Async handling during initialization

## [v1.4.0] - 2024-08-09
### Added
- Custom CA file path functionality to `UIConfigManager` class
- SSL verification checks that allow users to append a certificate path to the default CA file
- `pathlib.Path` objects for cross-platform functionality
- Latest version column added to datasets for exporting [#21](https://github.com/liquidz00/Patcher/issues/21)
- Support for logo file to be passed to use on generated PDF reports [#22](https://github.com/liquidz00/Patcher/issues/22)

### Changed
- Completion percent calculation is handled by `PatchTitle` class
- Prompt for setup method at runtime

### Removed
- `Delete` privileges from `ApiRole` model class
- Redundant calls to `click.Abort()`

### Fixed
- Animation class raises the exception that was caught
- Ensure tracebacks are written to log instead of `stderr`

## [v1.3.4] - 2024-07-29
### Added
- `--reset` flag to trigger setup assistant manually
- `format` and `clean` options to Makefile
- Functionality to delete stored credentials and `JamfClient` objects

### Changed
- Check for setup completion before executing `--reset`
- Logger objects are tied to specific class instances (child loggers)
- `LogMe` class creates child loggers during init

### Fixed
- `--omit` and `--sort` flags leverage `PatchTitle` class
- Sorting handles AttributeErrors gracefully
- Logger references fixed throughout

## [v1.3.3] - 2024-07-06
### Added
- Reference for report customization
- Additional static badges to README.md
- Functionality to publish to TestPyPI on pushes to `develop` branch

### Fixed
- Dynamic versioning during builds
- Relative import statements for package

## [v1.3.2] - 2024-07-05
### Added
- Functionality to dynamically create `config.ini` file on first launch
- `JamfClient` class, and URL validation function
- `cred_check` wrapper to ensure credentials are present when invoking CLI
- `PlistError` class to custom exceptions for error handling
- `asyncclick` library for asynchronous support

### Changed
- Project structure; leverage `src/patcher` directory and refactor references
- iOS version data calculation is handled by the `ReportManager` class
- First run wrapper includes welcome messaging by default
- Time zone conversion method moved to static method
- `ConfigManager` class leverages `keyring` library for environment variable handling
- Max concurrency defaults to 5 connections per Jamf API [scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices#rate-limiting)

### Removed
- `.env` and `ui_config.py` usage in favor of `keyring` and `config.ini`
- All references to `.env` file

### Fixed
- `ConfigManager` instance return values
- Incorrect log directory path references

## [v1.3.1] - 2024-06-22
### Added
- `--debug` (or `-x`) flag to view debug logs in `stdout` instead of default Animation
- Token expiration to `globals.py`

### Removed
- `threading.Event` from `LogMe` class configuration

## [v1.3.0] - 2024-06-18
### Added
- API Privilege error class
- Custom exceptions for error handling
- Functionality to calculate the amount of devices on the latest version of their respective OS
- `--ios` flag to include iOS device data in exported reports
- iOS version reporting functionality using Jamf Pro API and [SOFA](https://sofa.macadmins.io) feeds
- Functionality to retrieve mobile device IDs and operating systems from Jamf Classic API
- Bearer Token lifetime checks, Bearer Token expiration written to `.env` file by default

### Changed
- API Role requirements
- Custom exceptions are raised instead during error handling
- `check_token_lifetime` function defaults to `client_id` in `.env`

### Deprecated
- `datetime.utcnow()` deprecated as of Python 3.12 (Gabriel Sroka [@gabrielsroka](https://github.com/gabrielsroka))

### Fixed
- Issue with iOS device export
- Error handling when Token refresh response is `None`
- Issue with Animation continuing after error handling
- Properly await token lifetime checks

### Security
- Patched `urllib3` per [CVE-2024-37891](https://github.com/advisories/GHSA-34jh-p97f-mpxf)
- Patched `requests` per [CVE-2024-35195](https://github.com/advisories/GHSA-9wx4-h78v-vm56)

## [v1.2.1] - 2024-05-11
### Added
- Homebrew Python checks to `installer.sh`
- Traps for `SIGINT` and `SIGTERM`, checks for `.git` configuration on reinstall (#16)

## [v1.2.0] - 2024-04-16
### Added
- Check for `v0` install, attempts to copy `.env` file and fonts directory if found
- `sudo` and `root` checks to install. `-d` or `--develop` arguments passed will download develop branch instead of default

### Changed
- Wrap path in quotes to prevent globbing/word splitting
- Move `uninstall.sh` to tools subdirectory
- `installer.sh` location

### Security
- Patched `idna` per [CVE-2024-3651](https://github.com/advisories/GHSA-jjg7-2v4v-x38h)

## [v1.1.0] - 2024-04-04
### Added
- Release badge
- Bearer Token validation logic and fetching new tokens
- Animation functionality to format error and success messages to `stdout`
- `--user` flag to requirements installation

### Changed
- Date header now includes day by default, additional date formats can be passed with `--date-format` option [#7](https://github.com/liquidz00/Patcher/issues/7)
- Project directory is no longer hidden by default
- Custom fonts are copied into project directory instead of referencing
- Logs are written to log file instead of nested `data` directory

### Removed
- Symlink creation during install

### Security
- Updated pillow per CVE-2024-28219

## [v1.0.0] - 2024-03-28
### Added
- Initial version of Patcher
