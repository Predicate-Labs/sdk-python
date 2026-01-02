"""Tests for TraceFileManager.extract_stats method"""

from datetime import datetime, timezone

import pytest

from sentience.models import TraceStats
from sentience.trace_file_manager import TraceFileManager


def test_extract_stats_empty_events():
    """Test extract_stats with empty events list."""
    stats = TraceFileManager.extract_stats([])
    assert stats.total_steps == 0
    assert stats.total_events == 0
    assert stats.duration_ms is None
    assert stats.final_status == "unknown"
    assert stats.started_at is None
    assert stats.ended_at is None


def test_extract_stats_with_run_start_and_end():
    """Test extract_stats calculates duration from run_start and run_end."""
    start_time = datetime.now(timezone.utc)
    end_time = datetime.now(timezone.utc)
    # Make end_time 5 seconds later
    end_time = end_time.replace(second=end_time.second + 5)

    events = [
        {
            "type": "run_start",
            "ts": start_time.isoformat().replace("+00:00", "Z"),
            "data": {},
        },
        {
            "type": "step_start",
            "data": {"step_index": 0},
        },
        {
            "type": "step_end",
            "data": {},
        },
        {
            "type": "run_end",
            "ts": end_time.isoformat().replace("+00:00", "Z"),
            "data": {"steps": 1},
        },
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.total_steps == 1
    assert stats.total_events == 4
    assert stats.duration_ms is not None
    assert stats.duration_ms >= 5000  # At least 5 seconds
    assert stats.started_at == start_time.isoformat().replace("+00:00", "Z")
    assert stats.ended_at == end_time.isoformat().replace("+00:00", "Z")
    assert stats.final_status == "success"  # Has step_end, no errors


def test_extract_stats_counts_steps():
    """Test extract_stats correctly counts steps from step_start events."""
    events = [
        {"type": "run_start", "ts": "2024-01-01T00:00:00Z", "data": {}},
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "step_end", "data": {}},
        {"type": "step_start", "data": {"step_index": 1}},
        {"type": "step_end", "data": {}},
        {"type": "step_start", "data": {"step_index": 2}},
        {"type": "step_end", "data": {}},
        {"type": "run_end", "ts": "2024-01-01T00:01:00Z", "data": {"steps": 3}},
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.total_steps == 3
    assert stats.total_events == 8


def test_extract_stats_infers_status_success():
    """Test extract_stats infers success status from step_end events."""
    events = [
        {"type": "run_start", "ts": "2024-01-01T00:00:00Z", "data": {}},
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "step_end", "data": {}},
        {"type": "run_end", "ts": "2024-01-01T00:01:00Z", "data": {}},
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.final_status == "success"


def test_extract_stats_infers_status_failure():
    """Test extract_stats infers failure status from error events."""
    events = [
        {"type": "run_start", "ts": "2024-01-01T00:00:00Z", "data": {}},
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "error", "data": {"message": "Something went wrong"}},
        {"type": "run_end", "ts": "2024-01-01T00:01:00Z", "data": {}},
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.final_status == "failure"


def test_extract_stats_infers_status_partial():
    """Test extract_stats infers partial status from errors with step_end."""
    events = [
        {"type": "run_start", "ts": "2024-01-01T00:00:00Z", "data": {}},
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "step_end", "data": {}},
        {"type": "step_start", "data": {"step_index": 1}},
        {"type": "error", "data": {"message": "Step 2 failed"}},
        {"type": "run_end", "ts": "2024-01-01T00:01:00Z", "data": {}},
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.final_status == "partial"


def test_extract_stats_uses_run_end_status():
    """Test extract_stats uses status from run_end event if present."""
    events = [
        {"type": "run_start", "ts": "2024-01-01T00:00:00Z", "data": {}},
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "error", "data": {"message": "Error"}},
        {
            "type": "run_end",
            "ts": "2024-01-01T00:01:00Z",
            "data": {"status": "partial"},  # Explicit status overrides inference
        },
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.final_status == "partial"  # Uses run_end status, not inferred "failure"


def test_extract_stats_with_custom_inference():
    """Test extract_stats uses custom status inference function."""
    def custom_inference(events, run_end):
        # Return a valid status value
        return "partial"

    events = [
        {"type": "run_start", "ts": "2024-01-01T00:00:00Z", "data": {}},
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "step_end", "data": {}},
        {"type": "run_end", "ts": "2024-01-01T00:01:00Z", "data": {}},
    ]

    stats = TraceFileManager.extract_stats(events, infer_status_func=custom_inference)
    assert stats.final_status == "partial"  # Uses custom inference instead of default "success"


def test_extract_stats_no_timestamps():
    """Test extract_stats handles missing timestamps gracefully."""
    events = [
        {"type": "step_start", "data": {"step_index": 0}},
        {"type": "step_end", "data": {}},
    ]

    stats = TraceFileManager.extract_stats(events)
    assert stats.total_steps == 1
    assert stats.duration_ms is None
    assert stats.started_at is None
    assert stats.ended_at is None

