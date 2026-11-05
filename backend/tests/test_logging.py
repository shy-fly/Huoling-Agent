"""Tests for logging and Project Recorder Agent."""
from app.agents.project_recorder import EventCategory, recorder
from app.observability.logging_config import setup_logging, LOG_DIR


def test_recorder_persists_audit():
    setup_logging()
    rid = recorder.record(
        EventCategory.DEV,
        "test_event",
        "unit test message",
        detail={"test": True},
        trace_id="test-trace-001",
    )
    assert rid is not None
    items = recorder.query(trace_id="test-trace-001", limit=10)
    assert any(i["event"] == "test_event" for i in items)


def test_log_dir_exists():
    setup_logging()
    assert LOG_DIR.exists()
