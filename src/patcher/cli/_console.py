"""
Shared Rich console singletons and palette constants for the Patcher CLI.

Every CLI module that wants to emit Rich-rendered output (panels, spinners,
tracebacks, styled text) should import :data:`console` and :data:`err_console`
from here. Constructing fresh ``Console()`` objects per callsite leads to
inconsistent width detection, mixed themes, and double-rendered output when
two consoles share the same terminal.

The palette constants mirror the fastmcp/cyclopts convention so every
migrated ``console.print`` callsite references a single source of truth.
"""

from contextlib import contextmanager

from rich.console import Console

console = Console()
err_console = Console(stderr=True)

INFO_STYLE = "cyan"
WARNING_STYLE = "yellow"
ERROR_STYLE = "red"
SUCCESS_STYLE = "green"
DIM_STYLE = "dim"
SPINNER_NAME = "dots"


class _NoOpStatus:
    """
    Stand-in for Rich's Status when animation is disabled (e.g. --debug runs).

    Mirrors the surface CLI code calls on a live status (update / start / stop)
    so callers never branch on whether animation is enabled.
    """

    def update(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


@contextmanager
def status(message: str = "Processing", *, enabled: bool = True, spinner: str = SPINNER_NAME):
    """
    Debug-aware Rich status spinner.

    Yields a live :class:`rich.status.Status` when ``enabled`` is True, or a
    no-op stand-in with the same ``update`` / ``start`` / ``stop`` surface when
    disabled. Use ``enabled=not debug`` so ``--debug`` runs skip the spinner and
    let log lines flow uninterrupted.

    :param message: Initial message rendered next to the spinner.
    :type message: str
    :param enabled: When False, yields a :class:`_NoOpStatus` instead of a live spinner.
    :type enabled: bool
    :param spinner: Name of the Rich spinner to render.
    :type spinner: str
    """
    if not enabled:
        yield _NoOpStatus()
        return
    with console.status(message, spinner=spinner) as live:
        yield live
