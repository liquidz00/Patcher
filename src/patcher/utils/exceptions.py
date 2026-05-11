class PatcherError(Exception):
    """Base exception class for exceptions with automatic traceback logging and concise error display."""

    default_message = "An error occurred"

    def __init__(self, message: str = None, **kwargs):
        self.message = message or self.default_message
        self.context = kwargs
        # Expose context entries as attributes so callers can do
        # `getattr(err, "not_found", False)` or `err.status_code` directly.
        # Without this, the 404 short-circuit in Installomator.match() (which
        # uses `getattr(e, "not_found", False)`) silently never fires.
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)
        self.formatted_message = self.format_message()
        super().__init__(self.formatted_message)

    def format_message(self) -> str:
        """Format exception message properly."""
        context_details = " | ".join(
            f"{key}: {value}" for key, value in self.context.items() if value
        )
        return f"{self.message} ({context_details})" if context_details else self.message

    def __str__(self):
        return self.formatted_message


class SetupError(PatcherError):
    """Raised if any errors occur during automatic setup."""

    pass


class CredentialError(PatcherError):
    """Raised if any errors occur during saving or updating credentials."""

    pass


class APIResponseError(PatcherError):
    """Raised when an API Call receives an unsuccessful status code."""

    pass


class ShellCommandError(PatcherError):
    """Raised when the return code of a subprocess exec call is non-zero."""

    pass


class TokenError(PatcherError):
    """Raised when there is an error fetching, saving or retrieving a bearer token from Jamf API."""

    pass


class InstallomatorWarning(Warning):
    """Custom warning to indicate Installomator-related issues."""

    pass
