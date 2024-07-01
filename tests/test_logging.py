import pytest
from unittest.mock import patch, MagicMock
from src.Patcher.logger import setup_child_logger, LogMe


@pytest.fixture
def mock_setup_child_logger():
    with patch("src.Patcher.logger.setup_child_logger") as mock:
        mock_logger = MagicMock()
        mock.return_value = mock_logger
        yield mock


# Test logging functionality - Info
def test_log_me_info(mock_setup_child_logger, capsys):
    mock_logger = mock_setup_child_logger.return_value
    log_me = LogMe(mock_logger)
    log_me.info("This is an info message")
    mock_logger.info.assert_called_once_with("This is an info message")

    captured = capsys.readouterr()
    assert "This is an info message" in captured.out


# Test logging functionality - Error
def test_log_me_error(mock_setup_child_logger, capsys):
    mock_logger = mock_setup_child_logger.return_value
    log_me = LogMe(mock_logger)
    log_me.error("This is an error message")
    mock_logger.error.assert_called_once_with("This is an error message")

    captured = capsys.readouterr()
    assert "This is an error message" in captured.err


def test_debug_logging_enabled(capture_logs):
    child_logger = setup_child_logger("patcher", "test_debug_enabled", debug=True)
    log_me = LogMe(child_logger)

    log_me.debug("This is a debug message")

    capture_logs.seek(0)
    assert "This is a debug message" in capture_logs.getvalue()


def test_debug_logging_disabled(capture_logs):
    child_logger = setup_child_logger("patcher", "test_debug_disabled")
    log_me = LogMe(child_logger)

    log_me.debug("This is a debug message when debug is disabled")

    capture_logs.seek(0)
    assert (
        "This is a debug message when debug is disabled" not in capture_logs.getvalue()
    )


def test_info_logging(capture_logs):
    child_logger = setup_child_logger("patcher", "test_debug_disabled")
    log_me = LogMe(child_logger)

    log_me.info("This is an info message")

    capture_logs.seek(0)
    assert "This is an info message" in capture_logs.getvalue()
