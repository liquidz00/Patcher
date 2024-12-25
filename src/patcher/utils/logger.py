import logging
import os
import platform
import sys
import traceback
from logging import LogRecord
from logging.handlers import RotatingFileHandler
from types import TracebackType
from typing import Optional, Type

import asyncclick as click


def format_traceback(
    exc_type: Type[BaseException], exc_value: BaseException, exc_traceback: Optional[TracebackType]
) -> str:
    """
    Format a traceback as a concise string for user-friendly console output.

    :param exc_type: The exception type.
    :type exc_type: Type[BaseException]
    :param exc_value: The exception instance.
    :type exc_value: BaseException
    :param exc_traceback: The traceback object.
    :type exc_traceback: Optional[TracebackType]
    :return: A formatted string representing the exception context.
    :rtype: str
    """
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    if tb_lines:
        # Show only the last 2-3 lines of the traceback for context
        concise_tb = "".join(tb_lines[-3:])
        return concise_tb.strip()
    return "No traceback available."


class UnifiedLogHandler(logging.Handler):
    """Custom logging handler to write logs to macOS Unified Logs using the ``logger`` command."""

    def emit(self, record: LogRecord) -> None:
        """
        Emit a log message to macOS Unified Logs.

        :param record: The log record to emit.
        :type record: LogRecord
        """
        if platform.system() != "Darwin":
            return  # macOS only

        # Format the message using logger's formatter
        try:
            message = self.format(record)
            os.system(f"logger -t {PatcherLog.LOGGER_NAME} '{message}'")
        except Exception:
            self.handleError(record)


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
        :type name: Optional[str]
        :param level: Logging level, defaults to INFO if not specified.
        :type level: Optional[int]
        :param debug: Whether to enable debug logging for console, defaults to False.
        :type debug: bool
        :return: The configured logger.
        :rtype: logging.logger
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

            # Console handler for user-facing messages
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
            logger.addHandler(console_handler)

            # UnifiedLogHandler for macOS
            if platform.system() == "Darwin":
                unified_handler = UnifiedLogHandler()
                unified_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
                unified_handler.setLevel(level or PatcherLog.LOG_LEVEL)
                logger.addHandler(unified_handler)

            logger.setLevel(logging.DEBUG)  # Capture all messages, delegate to handlers

        return logger

    @staticmethod
    def setup_child_logger(childName: str, loggerName: Optional[str] = None) -> logging.Logger:
        """
        Setup a child logger for a specified context.

        .. versionremoved:: 2.0

            The ``debug`` parameter is now handled at CLI entry point. Child loggers with an explicitly set logging level will not respect configuration changes to the root logger.

        :param childName: The name of the child logger.
        :type childName: str
        :param loggerName: The name of the parent logger, defaults to "Patcher".
        :type loggerName: str
        :return: The configured child logger.
        :rtype: logging.Logger
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
        :type exc_type: Type[BaseException]
        :param exc_value: The instance of the exception raised.
        :type exc_value: BaseException
        :param exc_traceback: The traceback object associated with the exception.
        :type exc_traceback: Optional[TracebackType]
        :raises SystemExit: Exits the program with status code 1 after handling the exception.
        """
        parent_logger = logging.getLogger(PatcherLog.LOGGER_NAME)
        child_logger = parent_logger.getChild("UnhandledException")
        child_logger.setLevel(parent_logger.level)

        if exc_type.__name__ == "KeyboardInterrupt":
            # Exit gracefully on keyboard interrupt
            child_logger.info("User interrupted the process.")
            sys.exit(130)  # SIGINT

        child_logger.error(
            "Unhandled exception occurred", exc_info=(exc_type, exc_value, exc_traceback)
        )

        # Show user-friendly message in console
        formatted_tb = format_traceback(exc_type, exc_value, exc_traceback)
        console_message = f"❌ {exc_type.__name__}: {exc_value}\n\nContext:\n{formatted_tb}"

        click.echo(
            click.style(console_message, fg="red", bold=True),
            err=True,
        )
        click.echo(
            f"💡 For more details, please check the log file at: {PatcherLog.LOG_FILE}",
            err=True,
        )
        sys.exit(1)


class LogMe:
    """
    A wrapper class for logging with optional output to console using click.

    :param class_name: The name of the class for which the logger is being set up.
    :type class_name: str
    :param debug: Whether to set the child logger level to DEBUG, defaults to False.
    :type debug: Optional[bool]
    """

    def __init__(self, class_name: str, debug: Optional[bool] = False):
        self.logger = PatcherLog.setup_child_logger(class_name)
        self.debug_enabled = debug

    def toggle_debug(self, enable: bool) -> None:
        """
        Dynamically enable or disable debug messages in the console.

        :param enable: Whether to enable debug output in the console.
        :type enable: bool
        """
        self.debug_enabled = enable
        console_handler = next(
            (h for h in self.logger.handlers if isinstance(h, logging.StreamHandler)), None
        )
        if console_handler:
            console_handler.setLevel(logging.DEBUG if enable else logging.WARNING)

    def debug(self, msg: str):
        self.logger.debug(msg)
        if self.debug_enabled:
            click.echo(click.style(f"\rDEBUG: {msg.strip()}", fg="magenta"))

    def info(self, msg: str):
        self.logger.info(msg)
        click.echo(click.style(f"\rINFO: {msg.strip()}", fg="blue"))

    def warning(self, msg: str):
        self.logger.warning(msg)
        click.echo(click.style(f"\rWARNING: {msg.strip()}", fg="yellow", bold=True))

    def error(self, msg: str, exc_info: Optional[BaseException] = None):
        self.logger.error(msg, exc_info=exc_info)
        if exc_info:
            formatted_tb = format_traceback(type(exc_info), exc_info, exc_info.__traceback__)
            console_message = f"ERROR: {msg}\n\nContext:\n{formatted_tb}"
        else:
            console_message = f"ERROR: {msg}"

        click.echo(click.style(console_message, fg="red", bold=True))
        click.echo(
            f"💡 For more details, please check the log file at: {PatcherLog.LOG_FILE}",
            err=True,
        )
