import click
from src.Patcher.logger import LogMe
from typing import AnyStr
from contextlib import contextmanager
from threading import Event


class PatcherError(Exception):
    """Base exception class for exceptions that should automatically raise click.Abort()"""

    def __init__(self, message: AnyStr, *args):
        super().__init__(message, *args)
        click.echo(click.style(f"\nError: {message}", fg="red", bold=True), err=True)
        raise click.Abort()


class TokenFetchError(PatcherError):
    """Raised when there is an error fetching a bearer token from Jamf API."""

    def __init__(self, message="Unable to fetch bearer token", reason=None):
        self.reason = reason
        if reason:
            message = f"{message} - Reason: {reason}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.reason:
            return f"{self.message} - Reason: {self.reason}"
        return self.message


class TokenLifetimeError(PatcherError):
    """Raised when the token lifetime is too short."""

    def __init__(self, message="Token lifetime is too short", lifetime=None):
        self.lifetime = lifetime
        if lifetime:
            message = f"{message} - Remaining Lifetime: {lifetime} seconds"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.lifetime:
            return f"{self.message} - Remaining Lifetime: {self.lifetime} seconds"
        return self.message


class DirectoryCreationError(PatcherError):
    """Raised when there is an error creating directories."""

    def __init__(self, message="Error creating directory", path=None):
        self.path = path
        if path:
            message = f"{message} - Path: {path}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.path:
            return f"{self.message} - Path: {self.path}"
        return self.message


class PlistError(PatcherError):
    """Raised when there is an error creating directories."""

    def __init__(self, message="Unable to interact with plist!", path=None):
        self.path = path
        if path:
            message = f"{message} - Path: {path}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.path:
            return f"{self.message} - Path: {self.path}"
        return self.message


class ExportError(PatcherError):
    """Raised when encountering error(s) exporting data to files."""

    def __init__(self, message="Error exporting data", file_path=None):
        self.file_path = file_path
        if file_path:
            message = f"{message} - File Path: {file_path}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.file_path:
            return f"{self.message} - File Path: {self.file_path}"
        return self.message


class PolicyFetchError(PatcherError):
    """Raised when unable to fetch policy IDs from Jamf instance"""

    def __init__(
        self, message="Error obtaining policy information from Jamf instance", url=None
    ):
        self.url = url
        if url:
            message = f"{message} - URL: {url}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.url:
            return f"{self.message} - URL: {self.url}"
        return self.message


class SummaryFetchError(PatcherError):
    """Raised when there is an error fetching summaries"""

    def __init__(
        self, message="Error obtaining patch summaries from Jamf instance", url=None
    ):
        self.url = url
        if url:
            message = f"{message} - URL: {url}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.url:
            return f"{self.message} - URL: {self.url}"
        return self.message


class DeviceIDFetchError(PatcherError):
    """Raised when there is an error fetching device IDs from Jamf instance"""

    def __init__(
        self, message="Error retreiving device IDs from Jamf instance", reason=None
    ):
        self.reason = reason
        if reason:
            message = f"{message} - Reason: {reason}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.reason:
            return f"{self.message} - Reason: {self.reason}"
        return self.message


class DeviceOSFetchError(PatcherError):
    """Raised when there is an error fetching device IDs from Jamf instance"""

    def __init__(
        self, message="Error retreiving OS information from Jamf instance", reason=None
    ):
        self.reason = reason
        if reason:
            message = f"{message} - Reason: {reason}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.reason:
            return f"{self.message} - Reason: {self.reason}"
        return self.message


class SortError(PatcherError):
    """Raised when there is an error fetching device IDs from Jamf instance"""

    def __init__(self, message="Invalid column name for sorting!", column=None):
        self.column = column
        if column:
            message = f"{message} - Column Provided: {column}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.column:
            return f"{self.message} - Column Provided: {self.column}"
        return self.message


class SofaFeedError(PatcherError):
    """Raised when there is an error fetching SOFA feed data"""

    def __init__(
        self,
        message="Unable to fetch SOFA feed",
        reason=None,
        url="https://sofa.macadmins.io/v1/ios_data_feed.json",
    ):
        self.reason = reason
        self.url = url
        if reason:
            message = f"{message} at {url} - Reason: {reason}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.reason:
            return f"{self.message} at {self.url} - Reason: {self.reason}"
        return self.message


class APIPrivilegeError(PatcherError):
    """Raised when the provided API client does not have sufficient privileges for API call type (commonly API integration checks)"""

    def __init__(
        self,
        message="API Client does not have sufficient privileges",
        reason=None,
    ):
        self.reason = reason
        if reason:
            message = f"{message} - Reason: {reason}"
        super().__init__(message)
        self.message = message

    def __str__(self):
        if self.reason:
            return f"{self.message} - Reason: {self.reason}"
        return self.message


@contextmanager
def error_handling(log: LogMe, stop_event: Event):
    default_exceptions = (
        TokenFetchError,
        TokenLifetimeError,
        DirectoryCreationError,
        ExportError,
        PolicyFetchError,
        SummaryFetchError,
        DeviceIDFetchError,
        DeviceOSFetchError,
        SortError,
        SofaFeedError,
        APIPrivilegeError,
        PlistError,
    )
    try:
        yield
    except default_exceptions as e:
        log.error(f"{e}")
        raise click.Abort()
    finally:
        stop_event.set()
