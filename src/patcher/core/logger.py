"""Patcher's logging: rotating file logs for all callers; the CLI adds console output separately."""

import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from types import TracebackType
from typing import Type


class PatcherLog:
    """Configures Patcher's stdlib rotating file logger (under Application Support)."""

    LOGGER_NAME = "Patcher"
    LOG_DIR = os.path.expanduser("~/Library/Application Support/Patcher/logs")
    LOG_FILE = os.path.join(LOG_DIR, "patcher.log")
    LOG_LEVEL = logging.INFO
    MAX_BYTES = 1048576 * 100  # 100 MB
    BACKUP_COUNT = 10

    @staticmethod
    def setup_logger(
        name: str | None = None,
        level: int | None = LOG_LEVEL,
    ) -> logging.Logger:
        """
        Configures and returns the Patcher logger with a rotating file handler.

        Pure stdlib, no terminal output. Console / colored output is installed
        separately by the CLI via :func:`patcher.cli._console.install_terminal_handler`;
        library callers get file logging only.

        :param name: Name of the logger, defaults to ``"Patcher"``.
        :type name: str | None
        :param level: Logging level for the file handler. Defaults to INFO.
        :type level: int | None
        :return: The configured logger.
        :rtype: ~logging.Logger
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
            logger.setLevel(logging.DEBUG)  # Capture all messages; handlers gate by level

        return logger

    @staticmethod
    def setup_child_logger(childName: str, loggerName: str | None = None) -> logging.Logger:
        """
        Setup a child logger for a specified context.

        :param childName: The name of the child logger.
        :type childName: str
        :param loggerName: The name of the parent logger, defaults to ``"Patcher"``.
        :type loggerName: str | None
        :return: The configured child logger.
        :rtype: ~logging.Logger
        """
        name = loggerName if loggerName else PatcherLog.LOGGER_NAME
        return logging.getLogger(name).getChild(childName)

    @staticmethod
    def custom_excepthook(
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        """
        Logs unhandled exceptions to Patcher's log file. Pure file logging, no
        terminal output. The CLI installs a chained excepthook that adds
        user-facing stderr messages on top of this one (see
        :func:`patcher.cli._console.install_terminal_excepthook`).

        ``KeyboardInterrupt`` is treated as a graceful exit (logged at INFO,
        process exits 130). All other uncaught exceptions are logged at ERROR.

        :param exc_type: The class of the exception raised.
        :type exc_type: ~typing.Type[BaseException]
        :param exc_value: The instance of the exception raised.
        :type exc_value: BaseException
        :param exc_traceback: The traceback object associated with the exception.
        :type exc_traceback: ~types.TracebackType | None
        """
        parent_logger = logging.getLogger(PatcherLog.LOGGER_NAME)
        child_logger = parent_logger.getChild("UnhandledException")
        child_logger.setLevel(parent_logger.level)

        if issubclass(exc_type, KeyboardInterrupt):
            child_logger.info("User interrupted the process.")
            sys.exit(130)  # SIGINT

        formatted_traceback = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        child_logger.error(
            f"Unhandled exception: {exc_type.__name__}: {exc_value}\n{formatted_traceback}"
        )


class LogMe:
    """Per-class logger wrapper (``self.log = LogMe(self.__class__.__name__)``)."""

    def __init__(self, class_name: str):
        """
        Thin wrapper around a stdlib :class:`logging.Logger` scoped to a class
        name. Adds nothing beyond the file logging configured by
        :meth:`PatcherLog.setup_logger`; terminal-color output is the CLI's
        responsibility.

        :param class_name: The name of the class for which the logger is being set up.
        :type class_name: str
        """
        self.logger = PatcherLog.setup_child_logger(class_name)

    def debug(self, msg: str):
        self.logger.debug(msg)

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)
