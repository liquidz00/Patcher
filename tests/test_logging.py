from src.logger import setup_child_logger, LogMe


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
