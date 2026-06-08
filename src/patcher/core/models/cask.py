"""Model for Homebrew Cask coverage matches."""

from . import Model


class CaskMatch(Model):
    """
    A name-only Homebrew Cask coverage stub.

    Records that a patch title matched a Homebrew Cask-sourced entry in the
    Patcher API catalog. This is the Homebrew analogue of the Installomator
    :class:`~patcher.core.models.label.Label` stub: it marks coverage from a
    second matching dimension without claiming an Installomator label exists.

    Cask-only catalog records carry no Installomator label, so a match here
    cannot be represented as a ``Label`` (whose ``installomator_label`` field
    is required). Keeping Cask coverage in its own model preserves the
    Installomator-only meaning of :attr:`~patcher.core.models.patch.PatchTitle.install_label`.

    :ivar name: The patch title this match is attached to (e.g.
        ``"Google Chrome"``).
    :type name: str
    :ivar token: The Homebrew Cask token (also the catalog slug) the title
        matched against (e.g. ``"google-chrome"``).
    :type token: str
    :ivar version: The Cask's current version, when the catalog resolved one.
    :type version: str | None
    :ivar download_url: The Cask's download URL, when present in the catalog.
    :type download_url: str | None
    """

    name: str
    token: str
    version: str | None = None
    download_url: str | None = None

    def __str__(self):
        return f"Name: {self.name} Cask: {self.token}"
