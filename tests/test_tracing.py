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
        assert event["data"]["status"] == "unknown"  # Default status


def test_tracer_emit_run_end_with_status():
    """Test Tracer.emit_run_end() with status parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_end(steps=5, status="success")

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "run_end"
        assert event["data"]["steps"] == 5
        assert event["data"]["status"] == "success"


def test_tracer_stats_tracking():
    """Test Tracer tracks execution statistics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)

            # Emit run_start (should track started_at)
            tracer.emit_run_start("TestAgent", "gpt-4")
            assert tracer.started_at is not None
            assert tracer.total_events == 1

            # Emit step_start (should track total_steps)
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            assert tracer.total_steps == 1
            assert tracer.total_events == 2

            tracer.emit_step_start("step-2", 2, "Goal 2", attempt=0)
            assert tracer.total_steps == 2
            assert tracer.total_events == 3

            # Emit run_end (should track ended_at)
            tracer.emit_run_end(steps=2)
            assert tracer.ended_at is not None
            assert tracer.total_events == 4

            # Get stats
            stats = tracer.get_stats()
            assert stats.total_steps == 2
            assert stats.total_events == 4
            assert stats.final_status == "unknown"
            assert stats.started_at is not None
            assert stats.ended_at is not None
            assert stats.duration_ms is not None
            assert stats.duration_ms >= 0


def test_tracer_set_final_status():
    """Test Tracer.set_final_status()."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)

            # Default status is "unknown"
            assert tracer.final_status == "unknown"

            # Set status
            tracer.set_final_status("success")
            assert tracer.final_status == "success"

            # Status should be included in run_end
            tracer.emit_run_end(steps=1)

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert event["data"]["status"] == "success"


def test_tracer_set_final_status_invalid():
    """Test Tracer.set_final_status() with invalid status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)

            # Invalid status should raise ValueError
            try:
                tracer.set_final_status("invalid")
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Invalid status" in str(e)


def test_jsonl_trace_sink_get_stats():
    """Test JsonlTraceSink.get_stats() extracts stats from trace file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            tracer.emit_step_start("step-2", 2, "Goal 2", attempt=0)
            tracer.emit_run_end(steps=2, status="success")

        # Get stats from sink
        stats = sink.get_stats()
        assert stats.total_steps == 2
        assert stats.total_events == 4
        assert stats.final_status == "success"
        assert stats.started_at is not None
        assert stats.ended_at is not None
        assert stats.duration_ms is not None


def test_tracer_auto_infers_final_status():
    """Test that Tracer automatically infers final_status from step outcomes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")

            # Emit successful step
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "click"}, step_id="step-1")

            # Emit another successful step
            tracer.emit_step_start("step-2", 2, "Goal 2", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "type"}, step_id="step-2")

            # Close without explicitly setting status or calling emit_run_end
            # Status should be auto-inferred as "success"
            tracer.close()

        # Verify status was auto-inferred
        assert tracer.final_status == "success"

        # Verify stats reflect the inferred status
        stats = tracer.get_stats()
        assert stats.final_status == "success"
        assert stats.total_steps == 2


def test_tracer_auto_infers_final_status_with_errors():
    """Test that Tracer automatically infers 'partial' status when there are both successes and errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")

            # Emit successful step
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "click"}, step_id="step-1")

            # Emit error
            tracer.emit_error("step-2", "Element not found", attempt=0)

            # Close without explicitly setting status
            tracer.close()

        # Verify status was auto-inferred as "partial" (has both successes and errors)
        assert tracer.final_status == "partial"

        # Verify stats reflect the inferred status
        stats = tracer.get_stats()
        assert stats.final_status == "partial"


def test_tracer_auto_infers_final_status_failure():
    """Test that Tracer automatically infers 'failure' status when there are only errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")

            # Emit error without any successful steps
            tracer.emit_error("step-1", "Element not found", attempt=0)

            # Close without explicitly setting status
            tracer.close()

        # Verify status was auto-inferred as "failure" (only errors, no successes)
        assert tracer.final_status == "failure"

        # Verify stats reflect the inferred status
        stats = tracer.get_stats()
        assert stats.final_status == "failure"


def test_tracer_auto_infer_does_not_override_explicit_status():
    """Test that auto-inference doesn't override explicitly set status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")

            # Emit successful step
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "click"}, step_id="step-1")

            # Explicitly set status to "partial" (even though we have success)
            tracer.set_final_status("partial")

            # Close - should not override explicit status
            tracer.close()

        # Verify explicit status was preserved
        assert tracer.final_status == "partial"

        # Verify stats reflect the explicit status
        stats = tracer.get_stats()
        assert stats.final_status == "partial"


def test_tracer_close_sets_final_status_automatically():
    """Test that tracer.close() automatically sets final_status if not explicitly set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")

            # Emit successful steps
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "click"}, step_id="step-1")

            tracer.emit_step_start("step-2", 2, "Goal 2", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "type"}, step_id="step-2")

            # Verify status is still "unknown" before close
            assert tracer.final_status == "unknown"

            # Close should auto-infer status
            tracer.close()

        # Verify status was auto-inferred after close
        assert tracer.final_status == "success"

        # Verify stats reflect the inferred status
        stats = tracer.get_stats()
        assert stats.final_status == "success"
        assert stats.total_steps == 2


def test_tracer_close_sets_final_status_in_run_end_event():
    """Test that tracer.close() sets final_status, and it's included in run_end if emit_run_end is called before close."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_run_start("TestAgent", "gpt-4")

            # Emit successful step
            tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
            tracer.emit("step_end", {"success": True, "action": "click"}, step_id="step-1")

            # Verify status is still "unknown" before emit_run_end
            assert tracer.final_status == "unknown"

            # emit_run_end should auto-infer status if not provided
            tracer.emit_run_end(steps=1)

            # Verify status was auto-inferred
            assert tracer.final_status == "success"

            # Close the tracer
            tracer.close()

        # Read trace file and verify run_end event has the inferred status
        lines = trace_path.read_text().strip().split("\n")
        run_end_events = [
            json.loads(line) for line in lines if json.loads(line).get("type") == "run_end"
        ]

        assert len(run_end_events) > 0
        # The run_end event should have the auto-inferred status
        last_run_end = run_end_events[-1]
        assert last_run_end["data"]["status"] == "success"


def test_tracer_close_with_cloud_sink_includes_final_status_in_completion():
    """Test that CloudTraceSink includes auto-inferred final_status in completion request."""
    from unittest.mock import Mock, patch

    from sentience.cloud_tracing import CloudTraceSink

    upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
    run_id = "test-close-status"
    api_key = "sk_test_123"

    sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)
    tracer = Tracer(run_id=run_id, sink=sink)

    tracer.emit_run_start("TestAgent", "gpt-4")

    # Emit successful step
    tracer.emit_step_start("step-1", 1, "Goal 1", attempt=0)
    tracer.emit("step_end", {"success": True, "action": "click"}, step_id="step-1")

    # Verify status is still "unknown" before close
    assert tracer.final_status == "unknown"

    with (
        patch("sentience.cloud_tracing.requests.put") as mock_put,
        patch("sentience.cloud_tracing.requests.post") as mock_post,
    ):
        # Mock successful trace upload
        mock_put.return_value = Mock(status_code=200)

        # Mock index upload (optional)
        mock_index_response = Mock()
        mock_index_response.status_code = 200
        mock_index_response.json.return_value = {"upload_url": "https://example.com/index"}

        # Mock completion response
        mock_complete_response = Mock()
        mock_complete_response.status_code = 200

        def post_side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            if "index_upload" in url:
                return mock_index_response
            return mock_complete_response

        mock_post.side_effect = post_side_effect

        # Close should auto-infer status and include it in completion request
        tracer.close()

        # Verify status was auto-inferred
        assert tracer.final_status == "success"

        # Verify completion request includes the inferred status
        complete_calls = [call for call in mock_post.call_args_list if "complete" in call[0][0]]
        assert len(complete_calls) > 0, "Completion request should have been called"

        complete_call = complete_calls[0]
        complete_data = complete_call[1].get("json", {})
        stats = complete_data.get("stats", {})

        assert stats["final_status"] == "success"

    # Cleanup
    cache_dir = Path.home() / ".sentience" / "traces" / "pending"
    trace_path = cache_dir / f"{run_id}.jsonl"
    if trace_path.exists():
        os.remove(trace_path)


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


# ============================================================================
# Tests for emit_snapshot() helper method
# ============================================================================


class MockSnapshot:
    """Mock snapshot object for testing emit_snapshot()."""

    def __init__(
        self,
        url: str = "https://example.com",
        screenshot: str | None = None,
        timestamp: str = "2024-01-01T00:00:00.000Z",
    ):
        self.url = url
        self.screenshot = screenshot
        self.timestamp = timestamp
        self.elements = []


def test_tracer_emit_snapshot_basic():
    """Test Tracer.emit_snapshot() emits snapshot event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            snapshot = MockSnapshot(url="https://example.com")
            tracer.emit_snapshot(
                snapshot=snapshot,
                step_id="step-456",
                step_index=1,
            )

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "snapshot"
        assert event["step_id"] == "step-456"
        assert event["data"]["url"] == "https://example.com"
        assert event["data"]["step_index"] == 1
        assert event["data"]["element_count"] == 0


def test_tracer_emit_snapshot_with_screenshot():
    """Test Tracer.emit_snapshot() includes screenshot_base64."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            # Raw base64 string (no data URL prefix)
            snapshot = MockSnapshot(
                url="https://example.com",
                screenshot="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
            )
            tracer.emit_snapshot(snapshot=snapshot, step_id="step-456")

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "snapshot"
        assert event["data"]["screenshot_base64"] == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        assert event["data"]["screenshot_format"] == "jpeg"


def test_tracer_emit_snapshot_with_data_url():
    """Test Tracer.emit_snapshot() extracts base64 from data URL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            # Data URL format (common from browser screenshot APIs)
            snapshot = MockSnapshot(
                url="https://example.com",
                screenshot="data:image/jpeg;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
            )
            tracer.emit_snapshot(snapshot=snapshot, step_id="step-456")

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        # Should extract just the base64 part (strip data URL prefix)
        assert event["data"]["screenshot_base64"] == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        assert event["data"]["screenshot_format"] == "jpeg"


def test_tracer_emit_snapshot_without_step_id():
    """Test Tracer.emit_snapshot() works without step_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            snapshot = MockSnapshot(url="https://example.com")
            tracer.emit_snapshot(snapshot=snapshot)

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["type"] == "snapshot"
        assert "step_id" not in event
        assert event["data"]["url"] == "https://example.com"


def test_tracer_emit_snapshot_none_snapshot():
    """Test Tracer.emit_snapshot() handles None snapshot gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            tracer.emit_snapshot(snapshot=None)

        # Should not emit anything for None snapshot
        content = trace_path.read_text().strip()
        assert content == ""


def test_tracer_emit_snapshot_custom_format():
    """Test Tracer.emit_snapshot() with custom screenshot format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"

        with JsonlTraceSink(trace_path) as sink:
            tracer = Tracer(run_id="test-run-123", sink=sink)
            snapshot = MockSnapshot(
                url="https://example.com",
                screenshot="iVBORw0KGgo...",
            )
            tracer.emit_snapshot(
                snapshot=snapshot,
                step_id="step-456",
                screenshot_format="png",
            )

        lines = trace_path.read_text().strip().split("\n")
        event = json.loads(lines[0])

        assert event["data"]["screenshot_format"] == "png"
