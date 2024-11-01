import logging
import os
import traceback
from logging import handlers
from typing import Optional

import asyncclick as click

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger_name = "Patcher"
default_log_level = logging.INFO
log_roll_size = 1048576 * 100
log_backupCount = 10


def setup_logger(
    log_name: Optional[str] = logger_name,
    log_filename: Optional[str] = f"{logger_name}.log",
    log_level: Optional[int] = default_log_level,
) -> logging.Logger:
    """
    Set up the main logger with rotating file handler.

    :param log_name: The name of the logger, defaults to 'patcher'.
    :type log_name: Optional[str]
    :param log_filename: The log file name, defaults to ``{log_name}.log``.
    :type log_filename: Optional[str]
    :param log_level: The logging level, defaults to logging.INFO.
    :type log_level: Optional[int]
    :return: The configured logger.
    :rtype: logging.Logger
    """
    log_path = os.path.abspath(
        os.path.join(os.path.expanduser("~/Library/Application Support/Patcher"), "logs")
    )
    if not os.path.isdir(log_path):
        os.makedirs(log_path)
    log_file = os.path.join(log_path, log_filename)
    handler = handlers.RotatingFileHandler(
        log_file, maxBytes=log_roll_size, backupCount=log_backupCount
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger(log_name)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(log_level)
    return logger


def setup_child_logger(
    name_of_child: str,
    name_of_logger: Optional[str] = logger_name,
    debug: Optional[bool] = False,
) -> logging.Logger:
    """
    Setup a child logger for a specified context.

    :param name_of_child: The name of the child logger.
    :type name_of_child: str
    :param name_of_logger: The name of the parent logger, defaults to 'patcher'
    :type name_of_logger: str
    :param debug: Whether to set the child logger level to DEBUG, defaults to False.
    :type debug: Optional[bool]
    :return: The configured child logger.
    :rtype: logging.Logger
    """
    child_logger = logging.getLogger(name_of_logger).getChild(name_of_child)
    if debug:
        child_logger.setLevel(logging.DEBUG)
    else:
        child_logger.setLevel(logging.INFO)
    return child_logger


logthis = setup_logger(logger_name, f"{logger_name}.log")


def handle_traceback(exception: Exception):
    """
    Write tracebacks to logs instead of to console for readability purposes.

    :param exception: The exception instance to log.
    :type exception: Exception
    """
    full_traceback = traceback.format_exc()
    logthis.error(f"Exception occurred: {str(exception)}\nTraceback:\n{full_traceback}")


class LogMe:
    """
    A wrapper class for logging with additional output to console using click.

    :param class_name: The name of the class for which the logger is being set up.
    :type class_name: str
    :param debug: Whether to set the child logger level to DEBUG, defaults to False.
    :type debug: Optional[bool]
    """

    def __init__(self, class_name: str, debug: Optional[bool] = False):
        self.logger = setup_child_logger(class_name, logger_name, debug)

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
            debug_out = click.style(text=f"DEBUG: {msg.strip()}", fg="magenta", bold=False)
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
        self.logger.error(msg)
        if self.is_debug_enabled():
            err_out = click.style(text=f"\rERROR: {msg.strip()}", fg="red", bold=True)
            click.echo(message=err_out, err=False)
