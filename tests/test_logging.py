from unittest.mock import MagicMock, patch

import pytest

from patcher.utils.logger import LogMe


@pytest.fixture
def mock_setup_child_logger():
    with patch("src.patcher.utils.logger.setup_child_logger") as mock:
        mock_logger = MagicMock()
        mock.return_value = mock_logger
        yield mock


# Test logging functionality - Info
def test_log_me_info(mock_setup_child_logger, capsys):
    mock_logger = mock_setup_child_logger.return_value
    log_me = LogMe("TestClass", debug=True)
    log_me.logger = mock_logger
    log_me.info("This is an info message")
    mock_logger.info.assert_called_once_with("This is an info message")

    captured = capsys.readouterr()
    assert "This is an info message" in captured.out


# Test logging functionality - Error
def test_log_me_error(mock_setup_child_logger, capsys):
    mock_logger = mock_setup_child_logger.return_value
    log_me = LogMe("TestClass", debug=True)
    log_me.logger = mock_logger
    log_me.error("This is an error message")
    mock_logger.error.assert_called_once_with("This is an error message")

    captured = capsys.readouterr()
    assert "This is an error message" in captured.err


def test_debug_logging_enabled(mock_setup_child_logger, capsys):
    child_logger = mock_setup_child_logger.return_value
    log_me = LogMe("TestClass", debug=True)
    log_me.logger = child_logger
    log_me.debug("This is a debug message")
    child_logger.debug.assert_called_once_with("This is a debug message")

    # capture_logs.seek(0)
    captured = capsys.readouterr()
    assert "This is a debug message" in captured.out


def test_debug_logging_disabled(mock_setup_child_logger, capsys):
    child_logger = mock_setup_child_logger.return_value
    child_logger.isEnabledFor.return_value = False
    log_me = LogMe("TestClass", debug=False)
    log_me.logger = child_logger
    log_me.debug("This is a debug message when debug is disabled")
    child_logger.debug.assert_called_once_with("This is a debug message when debug is disabled")

    captured = capsys.readouterr()
    print("Captured stdout:", captured.out)
    print("Captured stderr:", captured.err)

    assert "This is a debug message when debug is disabled" not in captured.out
