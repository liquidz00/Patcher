import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from types import TracebackType
from typing import Optional, Type

import asyncclick as click


class PatcherLog:
    LOGGER_NAME = "Patcher"
    LOG_DIR = os.path.expanduser("~/Library/Application Support/Patcher/logs")
    LOG_FILE = os.path.join(LOG_DIR, "patcher.log")
    LOG_LEVEL = logging.INFO
    MAX_BYTES = 1048576 * 100  # 100 MB
    BACKUP_COUNT = 10

    @staticmethod
    def setup_logger(
        name: Optional[str] = None,
        level: Optional[int] = LOG_LEVEL,
        debug: bool = False,
    ) -> logging.Logger:
        """
        Configures and returns a logger. If the logger is already configured, it ensures no duplicate handlers.

        :param name: Name of the logger, defaults to "Patcher".
        :type name: :py:obj:`~typing.Optional` [:py:class:`str`]
        :param level: Logging level, defaults to INFO if not specified.
        :type level: :py:obj:`~typing.Optional` [:py:class:`int`]
        :param debug: Whether to enable debug logging for console, defaults to False.
        :type debug: :py:class:`bool`
        :return: The configured logger.
        :rtype: :py:obj:`~logging.Logger`
        """
        logger_name = name if name else PatcherLog.LOGGER_NAME
        os.makedirs(PatcherLog.LOG_DIR, exist_ok=True)
        logger = logging.getLogger(logger_name)

        if not logger.hasHandlers():
            file_handler = RotatingFileHandler(
                PatcherLog.LOG_FILE,
                maxBytes=PatcherLog.MAX_BYTES,
                backupCount=PatcherLog.BACKUP_COUNT,
            )
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            file_handler.setLevel(level or PatcherLog.LOG_LEVEL)
            logger.addHandler(file_handler)

            # Console handler for user-facing messages if debug is True
            if debug:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
                console_handler.setLevel(logging.DEBUG)
                logger.addHandler(console_handler)

            logger.setLevel(logging.DEBUG)  # Capture all messages, delegate to handlers

        return logger

    @staticmethod
    def setup_child_logger(childName: str, loggerName: Optional[str] = None) -> logging.Logger:
        """
        Setup a child logger for a specified context.

        .. admonition:: Removed in version 2.0
            :class: danger

            The ``debug`` parameter is now handled at CLI entry point. Child loggers with an explicitly set logging level will not respect configuration changes to the root logger.

        :param childName: The name of the child logger.
        :type childName: :py:class:`str`
        :param loggerName: The name of the parent logger, defaults to "Patcher".
        :type loggerName: :py:class:`str`
        :return: The configured child logger.
        :rtype: :py:obj:`~logging.Logger`
        """
        name = loggerName if loggerName else PatcherLog.LOGGER_NAME
        return logging.getLogger(name).getChild(childName)

    @staticmethod
    def custom_excepthook(
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_traceback: Optional[TracebackType],
    ) -> None:
        """
        A custom exception handler for unhandled exceptions.

        This method is intended to be assigned to ``sys.excepthook`` to handle any uncaught exceptions in the application.

        :param exc_type: The class of the exception raised.
        :type exc_type: :py:obj:`~typing.Type` of :py:class:`BaseException`
        :param exc_value: The instance of the exception raised.
        :type exc_value: :py:class:`BaseException`
        :param exc_traceback: The traceback object associated with the exception.
        :type exc_traceback: :py:obj:`~typing.Optional` of :py:obj:`~types.TracebackType`
        """
        parent_logger = logging.getLogger(PatcherLog.LOGGER_NAME)
        child_logger = parent_logger.getChild("UnhandledException")
        child_logger.setLevel(parent_logger.level)

        if exc_type.__name__ == "KeyboardInterrupt":
            # Exit gracefully on keyboard interrupt
            child_logger.info("User interrupted the process.")
            sys.exit(130)  # SIGINT

        # format traceback
        formatted_traceback = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )

        child_logger.error(
            f"Unhandled exception: {exc_type.__name__}: {exc_value}\n{formatted_traceback}"
        )

        # Show user-friendly message in console
        console_message = f"❌ {exc_type.__name__}: {exc_value}"

        click.echo(
            click.style(console_message, fg="red", bold=True),
            err=True,
        )
        click.echo(
            f"💡 For more details, please check the log file at: '{PatcherLog.LOG_FILE}'",
            err=True,
        )
        return


class LogMe:
    def __init__(self, class_name: str):
        """
        A wrapper class for logging with optional output to console using click.

        :param class_name: The name of the class for which the logger is being set up.
        :type class_name: :py:class:`str`
        """
        self.logger = PatcherLog.setup_child_logger(class_name)

    @property
    def is_debug(self) -> bool:
        """Check if any logger handlers are set to debug level."""
        return any(h.level == logging.DEBUG for h in self.logger.handlers)

    def debug(self, msg: str):
        self.logger.debug(msg)
        if self.is_debug:
            click.echo(click.style(f"\rDEBUG: {msg.strip()}", fg="magenta"))

    def info(self, msg: str):
        self.logger.info(msg)
        if self.is_debug:
            click.echo(click.style(f"\rINFO: {msg.strip()}", fg="blue"))

    def warning(self, msg: str):
        self.logger.warning(msg)
        if self.is_debug:
            click.echo(click.style(f"\rWARNING: {msg.strip()}", fg="yellow", bold=True))

    def error(self, msg: str):
        # Error message formatting is handled by CLI, bypassing need to format error messages
        # at the class level
        self.logger.error(msg)
