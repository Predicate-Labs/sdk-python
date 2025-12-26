"""Tests for sentience.tracing module"""

import json
import tempfile
from pathlib import Path

from sentience.tracing import JsonlTraceSink, TraceEvent, Tracer


def test_trace_event_to_dict():
    """Test TraceEvent serialization to dict."""
    event = TraceEvent(
        v=1,
        type="test_event",
        ts="2024-01-01T00:00:00.000Z",
        run_id="test-run-123",
        seq=1,
        data={"key": "value"},
        step_id="step-456",
        ts_ms=1704067200000,
    )
    result = event.to_dict()
    assert result["v"] == 1
    assert result["type"] == "test_event"
    assert result["step_id"] == "step-456"
    assert result["data"]["key"] == "value"
    assert result["ts"] == "2024-01-01T00:00:00.000Z"
    assert result["run_id"] == "test-run-123"
    assert result["seq"] == 1
    assert result["ts_ms"] == 1704067200000


def test_trace_event_to_dict_optional_fields():
    """Test TraceEvent serialization without optional fields."""
    event = TraceEvent(
        v=1,
        type="test_event",
        ts="2024-01-01T00:00:00.000Z",
        run_id="test-run-123",
        seq=1,
        data={"key": "value"},
    )
    result = event.to_dict()
    assert "step_id" not in result
    assert "ts_ms" not in result


def test_jsonl_trace_sink_emit():
    """Test JsonlTraceSink emits valid JSONL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"
        sink = JsonlTraceSink(trace_path)

        # Emit two events
        sink.emit({"v": 1, "type": "event1", "seq": 1})
        sink.emit({"v": 1, "type": "event2", "seq": 2})
        sink.close()

        # Read and verify
        lines = trace_path.read_text().strip().split("\n")
        assert len(lines) == 2

        event1 = json.loads(lines[0])
        assert event1["type"] == "event1"
        assert event1["seq"] == 1

        event2 = json.loads(lines[1])
        assert event2["type"] == "event2"
        assert event2["seq"] == 2


def test_jsonl_trace_sink_context_manager():
    """Test JsonlTraceSink works as context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            sink.emit({"v": 1, "type": "test", "seq": 1})

        # File should be closed and flushed
        lines = trace_path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "test"


def test_tracer_emit():
    """Test Tracer emits events with auto-incrementing sequence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)

            tracer.emit("event1", {"data": "value1"})
            tracer.emit("event2", {"data": "value2"}, step_id="step-456")

        # Read and verify
        lines = trace_path.read_text().strip().split("\n")
        assert len(lines) == 2

        event1 = json.loads(lines[0])
        assert event1["type"] == "event1"
        assert event1["seq"] == 1
        assert event1["run_id"] == "test-run-123"
        assert event1["data"]["data"] == "value1"
        assert "step_id" not in event1

        event2 = json.loads(lines[1])
        assert event2["type"] == "event2"
        assert event2["seq"] == 2
        assert event2["step_id"] == "step-456"


def test_tracer_emit_run_start():
    """Test Tracer.emit_run_start()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start(
                agent="SentienceAgent",
                llm_model="gpt-4",
                config={"snapshot_limit": 50},
            )

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "run_start"
        assert event["data"]["agent"] == "SentienceAgent"
        assert event["data"]["llm_model"] == "gpt-4"
        assert event["data"]["config"]["snapshot_limit"] == 50


def test_tracer_emit_step_start():
    """Test Tracer.emit_step_start()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_step_start(
                step_id="step-456",
                step_index=1,
                goal="Click login button",
                attempt=0,
                pre_url="https://example.com",
            )

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "step_start"
        assert event["step_id"] == "step-456"
        assert event["data"]["step_id"] == "step-456"
        assert event["data"]["step_index"] == 1
        assert event["data"]["goal"] == "Click login button"
        assert event["data"]["attempt"] == 0
        assert event["data"]["pre_url"] == "https://example.com"


def test_tracer_emit_run_end():
    """Test Tracer.emit_run_end()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_end(steps=5)

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "run_end"
        assert event["data"]["steps"] == 5


def test_tracer_emit_error():
    """Test Tracer.emit_error()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_error(step_id="step-456", error="Element not found", attempt=1)

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "error"
        assert event["step_id"] == "step-456"
        assert event["data"]["step_id"] == "step-456"
        assert event["data"]["error"] == "Element not found"
        assert event["data"]["attempt"] == 1


def test_tracer_context_manager():
    """Test Tracer works as context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            with Tracer(run_id="test-run-123", sink=sink) as tracer:
                tracer.emit("test_event", {"data": "value"})

        # Verify file is closed and flushed
        lines = trace_path.read_text().strip().split("\n")
        assert len(lines) == 1
