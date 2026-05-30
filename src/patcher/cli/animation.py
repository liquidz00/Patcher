"""
Async-friendly spinner wrapper around :class:`rich.status.Status`.

``Animation`` keeps the same public surface the rest of the CLI was already
written against (constructor signature, ``start`` / ``stop`` / ``update_msg``
coroutines, ``error_handling`` async context manager, a ``stop_event`` attr
the report module flips defensively). The internals are now Rich, so output
goes through the shared :data:`patcher.cli._console.console` and renders the
same spinner everywhere.

Rich's ``Status`` is a sync context manager but its ``start`` / ``stop`` /
``update`` methods are safe to call directly from inside an event loop, so
the async wrappers here just dispatch to them.
"""

import asyncio
from contextlib import asynccontextmanager

from rich.status import Status

from ._console import console

SPINNER_NAME = "dots"


class Animation:
    def __init__(self, message_template: str = "Processing", enable_animation: bool = True):
        """
        Display an animated spinner with a message during long-running operations.

        :param message_template: Initial message rendered next to the spinner.
        :type message_template: str
        :param enable_animation: When False, all start / update / stop calls are
            no-ops. Used by ``--debug`` runs so spinner frames don't interleave
            with log output.
        :type enable_animation: bool
        """
        self.message_template = message_template
        self.enable_animation = enable_animation
        # Preserved for backwards compatibility. report.py defensively calls
        # `animation.stop_event.set()` after the error_handling block exits.
        self.stop_event = asyncio.Event()
        self._status: Status | None = None
        self._started = False

    async def start(self) -> None:
        """Start the Rich status spinner. No-op when animation is disabled or already running."""
        if not self.enable_animation or self._started:
            return
        self._status = console.status(self.message_template, spinner=SPINNER_NAME)
        self._status.start()
        self._started = True

    async def stop(self) -> None:
        """Stop the spinner and clear its line. Safe to call multiple times."""
        if self._status is not None and self._started:
            self._status.stop()
        self._started = False
        self._status = None
        self.stop_event.set()

    async def update_msg(self, new_message_template: str) -> None:
        """
        Swap the spinner's message in place.

        :param new_message_template: The new message to display alongside the spinner.
        :type new_message_template: str
        """
        self.message_template = new_message_template
        if self._status is not None and self._started:
            self._status.update(new_message_template)

    @asynccontextmanager
    async def error_handling(self):
        """
        Run a block of work with the spinner active.

        Starts the spinner on entry, stops it on exit (success or failure),
        and re-raises any exception so the caller's normal error handling
        path runs.
        """
        await self.start()
        try:
            yield
        finally:
            await self.stop()
