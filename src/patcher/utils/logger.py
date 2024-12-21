import logging
import os
import sys
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
        name: Optional[str] = None, level: Optional[int] = LOG_LEVEL
    ) -> logging.Logger:
        """
        Configures and returns a logger. If the logger is already configured, it ensures no duplicate handlers.

        :param name: Name of the logger, defaults to "Patcher".
        :type name: Optional[str]
        :param level: Logging level, defaults to INFO if not specified.
        :type level: Optional[int]
        :return: The configured logger.
        :rtype: logging.logger
        """
        logger_name = name if name else PatcherLog.LOGGER_NAME
        os.makedirs(PatcherLog.LOG_DIR, exist_ok=True)
        logger = logging.getLogger(logger_name)

        if not logger.hasHandlers():
            logger.setLevel(level or PatcherLog.LOG_LEVEL)

            file_handler = RotatingFileHandler(
                PatcherLog.LOG_FILE,
                maxBytes=PatcherLog.MAX_BYTES,
                backupCount=PatcherLog.BACKUP_COUNT,
            )
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            logger.addHandler(file_handler)

        return logger

    @staticmethod
    def setup_child_logger(
        childName: str, loggerName: Optional[str] = None, debug: Optional[bool] = False
    ) -> logging.Logger:
        """
        Setup a child logger for a specified context.

        :param childName: The name of the child logger.
        :type childName: str
        :param loggerName: The name of the parent logger, defaults to "Patcher".
        :type loggerName: str
        :param debug: Whether to set the child logger level to DEBUG, defaults to False.
        :type debug: bool
        :return: The configured child logger.
        :rtype: logging.Logger
        """
        name = loggerName if loggerName else PatcherLog.LOGGER_NAME
        child_logger = logging.getLogger(name).getChild(childName)
        child_logger.setLevel(logging.DEBUG) if debug else child_logger.setLevel(logging.INFO)
        return child_logger

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
        self.logger = PatcherLog.setup_child_logger(class_name, PatcherLog.LOGGER_NAME, debug)

    def is_debug_enabled(self) -> bool:
        """
        Check if debug logging is enabled.

        :return: True if debug logging is enabled, False otherwise.
        :rtype: bool
        """
        return self.logger.isEnabledFor(logging.DEBUG)

    def debug(self, msg: str):
        """
        Log a debug message and output to console if debug is enabled.

        :param msg: The debug message to log.
        :type msg: str
        """
        self.logger.debug(msg)
        if self.is_debug_enabled():
            debug_out = click.style(text=f"\rDEBUG: {msg.strip()}", fg="magenta", bold=False)
            click.echo(message=debug_out, err=False)

    def info(self, msg: str):
        """
        Log an info message and output to console.

        :param msg: The info message to log.
        :type msg: str
        """
        self.logger.info(msg)
        if self.is_debug_enabled():
            std_output = click.style(text=f"\rINFO: {msg.strip()}", fg="blue", bold=False)
            click.echo(message=std_output, err=False)

    def warning(self, msg: str):
        """
        Log a warning message and output to console.

        :param msg: The warning message to log.
        :type msg: str
        """
        self.logger.warning(msg)
        if self.is_debug_enabled():
            warn_out = click.style(text=f"\rWARNING: {msg.strip()}", fg="yellow", bold=True)
            click.echo(message=warn_out, err=False)

    def error(self, msg: str):
        """
        Log an error message and output to console.

        :param msg: The error message to log.
        :type msg: str
        """
        self.logger.error(msg, exc_info=True)
        if self.is_debug_enabled():
            err_out = click.style(text=f"\rERROR: {msg.strip()}", fg="red", bold=True)
            click.echo(message=err_out, err=False)
