from typing import AnyStr, Optional

import click

from .logger import handle_traceback


class PatcherError(Exception):
    """Base exception class for exceptions with automatic traceback logging and concise error display."""

    default_message = "An error occurred"

    def __init__(self, message: AnyStr = None, **kwargs):
        self.message = message or self.default_message
        self.details = kwargs
        self.message = self.format_message()
        super().__init__(self.message)
        self.log_traceback()
        self.display_message()

    def log_traceback(self):
        """Log the traceback of the exception. See :meth:`~patcher.utils.logger.handle_traceback`."""
        handle_traceback(self)

    def display_message(self):
        """Display the error message to the console."""
        click.echo(click.style(f"\nError: {self.message}", fg="red", bold=True), err=True)

    def format_message(self) -> str:
        """Format exception message properly."""
        details = " - ".join(
            f"{key}: {value}" for key, value in self.details.items() if value is not None
        )
        if details:
            return f"{self.message} - {details}"
        return self.message

    def __str__(self):
        return self.message


class CredentialDeletionError(PatcherError):
    """Raised when there is a specified credential could not be removed from keychain."""

    default_message = "Unable to delete credential"

    def __init__(self, cred: Optional[AnyStr] = None):
        super().__init__(cred=cred)


class TokenFetchError(PatcherError):
    """Raised when there is an error fetching a bearer token from Jamf API."""

    default_message = "Unable to fetch bearer token"

    def __init__(self, reason: Optional[AnyStr] = None):
        super().__init__(reason=reason)


class TokenLifetimeError(PatcherError):
    """Raised when the token lifetime is too short."""

    default_message = "Token lifetime is too short"

    def __init__(self, lifetime: Optional[int] = None):
        super().__init__(lifetime=lifetime)


class DirectoryCreationError(PatcherError):
    """Raised when there is an error creating directories."""

    default_message = "Error creating directory"

    def __init__(self, path: Optional[AnyStr] = None):
        super().__init__(path=path)


class PlistError(PatcherError):
    """Raised when there is an error interacting with plist."""

    default_message = "Unable to interact with plist"

    def __init__(self, path: Optional[AnyStr] = None):
        super().__init__(path=path)


class ExportError(PatcherError):
    """Raised when encountering error(s) exporting data to files."""

    default_message = "Error exporting data"

    def __init__(self, file_path: Optional[AnyStr] = None):
        super().__init__(file_path=file_path)


class PolicyFetchError(PatcherError):
    """Raised when unable to fetch policy IDs from the Jamf instance."""

    default_message = "Error obtaining policy information from Jamf instance"

    def __init__(self, url: Optional[AnyStr] = None):
        super().__init__(url=url)


class SummaryFetchError(PatcherError):
    """Raised when there is an error fetching summaries."""

    default_message = "Error obtaining patch summaries from Jamf instance"

    def __init__(self, url: Optional[AnyStr] = None):
        super().__init__(url=url)


class DeviceIDFetchError(PatcherError):
    """Raised when there is an error fetching device IDs from the Jamf instance."""

    default_message = "Error retrieving device IDs from Jamf instance"

    def __init__(self, reason: Optional[AnyStr] = None):
        super().__init__(reason=reason)


class DeviceOSFetchError(PatcherError):
    """Raised when there is an error fetching device OS information from the Jamf instance."""

    default_message = "Error retrieving OS information from Jamf instance"

    def __init__(self, reason: Optional[AnyStr] = None):
        super().__init__(reason=reason)


class SortError(PatcherError):
    """Raised when there is an error sorting columns."""

    default_message = "Invalid column name for sorting"

    def __init__(self, column: Optional[AnyStr] = None):
        super().__init__(column=column)


class SofaFeedError(PatcherError):
    """Raised when there is an error fetching SOFA feed data."""

    default_message = "Unable to fetch SOFA feed"

    def __init__(
        self,
        reason: Optional[AnyStr] = None,
        url: AnyStr = "https://sofa.macadmins.io/v1/ios_data_feed.json",
    ):
        super().__init__(reason=reason, url=url)


class APIPrivilegeError(PatcherError):
    """Raised when the provided API client does not have sufficient privileges for API call type."""

    default_message = "API Client does not have sufficient privileges"

    def __init__(self, reason: Optional[AnyStr] = None):
        super().__init__(reason=reason)
