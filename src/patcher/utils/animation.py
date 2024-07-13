import asyncio
from contextlib import asynccontextmanager
from typing import AnyStr

import click

from .exceptions import *
from .logger import LogMe


class Animation:
    def __init__(self, message_template: AnyStr = "Processing", enable_animation: bool = True):
        """
        Initialize the Animation object.

        :param message_template: The base message to display.
        :param enable_animation: Flag to enable or disable animation.
        """
        self.stop_event = asyncio.Event()
        self.message_template = message_template
        self.enable_animation = enable_animation
        self.task = None
        self.lock = asyncio.Lock()
        self.spinner_chars = ["\u25E4", "\u25E5", "\u25E2", "\u25E3"]
        self.colors = ["cyan", "magenta", "bright_cyan", "bright_magenta"]
        self.last_message_length = 0

    async def start(self):
        """Start the animation as an asyncio task."""
        if not self.enable_animation:
            return

        self.task = asyncio.create_task(self._animate())

    async def stop(self):
        """Stop the animation and wait for the task to finish."""
        if self.task:
            self.stop_event.set()
            await self.task

    async def update_msg(self, new_message_template: AnyStr):
        """Update the message template."""
        async with self.lock:
            clear_message = "\r" + " " * self.last_message_length + "\r"
            click.echo(clear_message, nl=False)
            self.message_template = new_message_template

    async def _animate(self):
        """Animate a rotating spinner in the message template."""
        i = 0
        color_index = 0
        max_length = 0
        while not self.stop_event.is_set():
            async with self.lock:
                spinner = self.spinner_chars[i % len(self.spinner_chars)]
                color = self.colors[color_index % len(self.colors)]
                colored_spinner = click.style(spinner, fg=color)
                message = f"\r{self.message_template} {colored_spinner}"
                self.last_message_length = len(message)
                max_length = max(max_length, len(message))
                click.echo(message, nl=False)
                i += 1
                color_index += 1
            await asyncio.sleep(0.2)

        # Clear animation line after stopping
        click.echo("\r" + " " * max_length + "\r", nl=False)

    @asynccontextmanager
    async def error_handling(self, log: LogMe):
        """
        Context manager for error handling with animation.

        :param log: The log object for logging errors.
        """
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

        await self.start()
        try:
            yield
        except default_exceptions as e:
            log.error(f"{e}")
            raise click.Abort()
        finally:
            await self.stop()
