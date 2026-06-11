"""Patcher's exception hierarchy."""


class PatcherError(Exception):
    """
    Base exception class for Patcher exceptions.

    Carries arbitrary keyword context (e.g. ``status_code=401``, ``url=...``,
    ``not_found=True``) and renders it into the formatted message as
    ``message (key1: val1 | key2: val2)``.

    .. important::
        **Each keyword** in ``kwargs`` **is also set as an instance attribute**
        (see the loop below). This is load-bearing; multiple callers rely
        on ``getattr(err, "not_found", False)`` to short-circuit on 404
        responses (notably during Installomator label fetches).
        Removing the ``setattr`` loop in favor of "just storing kwargs in
        ``self.context``" looks like cleanup but silently breaks the 404
        short-circuit. The context dict is preserved separately for the
        message formatter.
    """

    default_message = "An error occurred"
    # Presentation-only context. Kept as attributes for the CLI to render
    # separately (see cli.format_err) but excluded from the message string.
    presentation_keys = frozenset({"recovery", "remediation"})

    def __init__(self, message: str = None, **kwargs):
        self.message = message or self.default_message
        self.context = kwargs
        # Expose context entries as attributes; see the class docstring's
        # `.. important::` note. Load-bearing for the 404 short-circuit.
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)
        self.formatted_message = self.format_message()
        super().__init__(self.formatted_message)

    def format_message(self) -> str:
        """Format exception message properly."""
        context_details = " | ".join(
            f"{key}: {value}"
            for key, value in self.context.items()
            if value and key not in self.presentation_keys
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


class TokenError(PatcherError):
    """Raised when there is an error fetching, saving or retrieving a bearer token from Jamf API."""

    pass


class InstallomatorWarning(Warning):
    """Custom warning to indicate InstallomatorClient-related issues."""

    pass
