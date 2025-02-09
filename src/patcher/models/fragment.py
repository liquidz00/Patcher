from urllib.parse import urlparse

from pydantic import field_validator, model_validator

from ..utils.exceptions import PatcherError
from . import Model


class Fragment(Model):
    """
    # TODO
    """

    name: str
    sha: str
    url: str
    html_url: str
    git_url: str
    download_url: str

    @field_validator("name")
    def validate_name(cls, value: str) -> str:
        """Ensures name ends in '.sh' as expected."""
        if not value.endswith(".sh"):
            raise PatcherError("Installomator name must end in '.sh'", received=value)
        return value

    @field_validator("sha")
    def validate_sha(cls, value: str) -> str:
        """Ensure the SHA is a valid SHA-1 hash."""
        if len(value) != 40 or not all(c in "0123456789abcdef" for c in value.lower()):
            raise PatcherError("Invalid SHA-1 hash received in Fragment object.", received=value)
        return value

    @field_validator("url", "html_url", "git_url", "download_url", mode="before")
    def validate_urls(cls, value: str) -> str:
        """
        Ensures all URL attributes are formatted properly.

        .. note::

            We are intentionally not using `pydantic.HttpUrl <https://docs.pydantic.dev/latest/api/networks/#pydantic.networks.HttpUrl>`_ objects as this would require typecasting all URL attributes as string down the call stack. This method leverages similar validation logic to ensure proper URL formatting.

        :param value: The specific ``*URL`` value to validate.
        :type value: :py:class:`str`
        :return: The properly formatted URL.
        :rtype: :py:class:`str`
        :raises PatcherError: If value fails validation due to improper HTTP scheme or netloc.
        """
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise PatcherError(
                "Invalid URL scheme detected in Fragment object - Must be HTTP/HTTPS.",
                received=value,
            )
        if not parsed.netloc:
            raise PatcherError("Invalid URL in Fragment object (invalid host).", received=value)
        return value

    @model_validator(mode="after")
    def validate_git_url_sha(self) -> "Fragment":
        """Ensures the SHA in the ``gitURL`` attribute matches the provided SHA-1 hash."""
        expected_sha = self.git_url.split("/")[-1]
        if self.sha != expected_sha:
            raise PatcherError(
                "SHA mismatch detected in Fragment object.",
                provided_sha=self.sha,
                extracted_sha=expected_sha,
            )
        return self

    @model_validator(mode="after")
    def validate_download_url(self) -> "Fragment":
        """Ensures ``self.name`` is included in ``self.downloadURL``."""
        if not self.download_url.endswith(self.name):
            raise PatcherError(
                "Download URL mismatch in Fragment object.", provided_url=self.download_url
            )
        return self
