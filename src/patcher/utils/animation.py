import asyncio
import inspect
from contextlib import asynccontextmanager
from typing import AnyStr

import click

from . import exceptions
from .logger import LogMe


class Animation:
    """
    Handles displaying an animated spinner with a message during long-running operations.

    The ``Animation`` class provides a simple way to display a rotating spinner along with
    a customizable message in the terminal, which can be useful for indicating progress
    in asynchronous tasks.
    """

    def __init__(self, message_template: AnyStr = "Processing", enable_animation: bool = True):
        """
        Initialize the Animation object.

        Sets up the necessary attributes for controlling the animation, including the
        message template, the spinner characters, and the color scheme.

        :param message_template: The base message to display alongside the spinner.
        :type message_template: AnyStr
        :param enable_animation: Flag to enable or disable the spinner animation.
        :type enable_animation: bool
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
        """
        Start the animation as an asyncio task.

        This method initiates the spinner animation in an asynchronous task. If
        animation is disabled, this method does nothing.
        """
        if not self.enable_animation:
            return

        self.task = asyncio.create_task(self._animate())

    async def stop(self):
        """
        Stop the animation and wait for the task to finish.

        This method stops the spinner animation by setting the stop event and
        waiting for the animation task to complete.
        """
        if self.task:
            self.stop_event.set()
            await self.task

    async def update_msg(self, new_message_template: AnyStr):
        """
        Update the message template.

        This method updates the message displayed alongside the spinner, clearing the
        previous message before displaying the new one.

        :param new_message_template: The new message to display alongside the spinner.
        :type new_message_template: AnyStr
        """
        async with self.lock:
            clear_message = "\r" + " " * self.last_message_length + "\r"
            click.echo(clear_message, nl=False)
            self.message_template = new_message_template

    async def _animate(self):
        """
        Animate a rotating spinner in the message template.

        This private method handles the actual animation of the spinner, cycling through
        a set of characters and colors while the stop event is not set. It runs in an
        asynchronous loop, updating the spinner and message at regular intervals.
        """
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

        This context manager starts the spinner animation when entering the context,
        and stops it when exiting. If an exception occurs within the context, it is
        logged and then re-raised.

        :param log: The logger object used to log any errors that occur within the context.
        :type log: LogMe
        """
        default_exceptions = tuple(
            cls
            for _, cls in inspect.getmembers(exceptions, inspect.isclass)
            if issubclass(cls, Exception)
        )

        await self.start()
        try:
            yield
        except default_exceptions as e:
            log.error(f"{e}")
            raise
        finally:
            await self.stop()
