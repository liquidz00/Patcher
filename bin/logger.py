import logging
import os
from logging import handlers
from typing import AnyStr
from click import echo, style

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger_name = "patcher"
default_log_level = logging.INFO
log_roll_size = 1048576 * 100
log_backupCount = 10


def setup_logger(
    log_name=logger_name, log_filename=f"{logger_name}.log", log_level=default_log_level
):
    log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
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

def setup_child_logger(name_of_logger, name_of_child):
    return logging.getLogger(name_of_logger).getChild(name_of_child)

logthis = setup_logger(logger_name, f"{logger_name}.log")


class LogMe:
    def __init__(self, logger):
        self.logger = logger

    def info(self, msg: AnyStr):
        self.logger.info(msg)
        std_output = style(text=f"\n{msg}", bold=False)
        echo(message=std_output, err=False)

    def warn(self, msg: AnyStr):
        self.logger.warning(msg)
        warn_out = style(text=f"\n{msg}", fg="yellow", bold=True)
        echo(message=warn_out, err=False)

    def error(self, msg: AnyStr):
        self.logger.error(msg)
        err_out = style(text=f"\n{msg}", fg="red", bold=True)
        echo(message=err_out, err=True)
