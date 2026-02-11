"""
Tests for trace indexing functionality.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from predicate.trace_indexing import (
    StepIndex,
    TraceIndex,
    build_trace_index,
    read_step_events,
    write_trace_index,
)


class TestTraceIndexing:
    """Test trace index building and querying."""

    def test_empty_trace(self):
        """Index of empty file should have zero events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "empty.jsonl"
            trace_path.write_text("")

            index = build_trace_index(str(trace_path))

            assert isinstance(index, TraceIndex)
            assert index.version == 1
            assert index.run_id == "empty"
            assert index.summary.event_count == 0
            assert index.summary.step_count == 0
            assert index.summary.error_count == 0
            assert len(index.steps) == 0

    def test_single_step_trace(self):
        """Index should have 1 step with correct offsets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "single-step.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {"goal": "Test goal"},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"type": "CLICK", "target_element_id": 42, "success": True},
                },
                {
                    "v": 1,
                    "type": "step_end",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {
                        "v": 1,
                        "step_id": "step-1",
                        "step_index": 1,
                        "goal": "Test goal",
                        "attempt": 0,
                        "pre": {"url": "https://example.com", "snapshot_digest": "sha256:test"},
                        "llm": {"response_text": "CLICK(42)", "response_hash": "sha256:test"},
                        "exec": {
                            "success": True,
                            "action": "click",
                            "outcome": "Action executed",
                            "duration_ms": 100,
                        },
                        "post": {"url": "https://example.com"},
                        "verify": {"passed": True, "signals": {}},
                    },
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.event_count == 3
            assert index.summary.step_count == 1
            assert len(index.steps) == 1

            step = index.steps[0]
            assert isinstance(step, StepIndex)
            assert step.step_id == "step-1"
            assert step.step_index == 1
            assert step.goal == "Test goal"
            assert step.status == "success"
            assert step.counters.events == 3
            assert step.counters.actions == 1
            assert step.offset_start == 0
            assert step.offset_end > step.offset_start

    def test_multi_step_trace(self):
        """Index should have multiple steps in order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "multi-step.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {"goal": "First step"},
                },
                {
                    "v": 1,
                    "type": "step_end",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-2",
                    "data": {"goal": "Second step"},
                },
                {
                    "v": 1,
                    "type": "step_end",
                    "ts": "2025-12-29T10:00:03.000Z",
                    "step_id": "step-2",
                    "data": {},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.step_count == 2
            assert len(index.steps) == 2
            assert index.steps[0].step_id == "step-1"
            assert index.steps[0].step_index == 1
            assert index.steps[1].step_id == "step-2"
            assert index.steps[1].step_index == 2

    def test_byte_offset_accuracy(self):
        """Seeking to offset should return exact events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "offset-test.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"type": "CLICK"},
                },
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-2",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:03.000Z",
                    "step_id": "step-2",
                    "data": {"type": "TYPE"},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            # Read step-1 events using offset
            step1 = index.steps[0]
            step1_events = read_step_events(str(trace_path), step1.offset_start, step1.offset_end)

            assert len(step1_events) == 2
            assert step1_events[0]["step_id"] == "step-1"
            assert step1_events[0]["type"] == "step_start"
            assert step1_events[1]["step_id"] == "step-1"
            assert step1_events[1]["type"] == "action"

            # Read step-2 events using offset
            step2 = index.steps[1]
            step2_events = read_step_events(str(trace_path), step2.offset_start, step2.offset_end)

            assert len(step2_events) == 2
            assert step2_events[0]["step_id"] == "step-2"
            assert step2_events[1]["type"] == "action"

    def test_snapshot_digest_determinism(self):
        """Same snapshot data should produce same digest."""
        snapshot_data = {
            "url": "https://example.com",
            "viewport": {"width": 1920, "height": 1080},
            "elements": [
                {
                    "id": 1,
                    "role": "button",
                    "text": "Click me",
                    "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0},
                    "is_primary": True,
                    "is_clickable": True,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "digest-test.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "snapshot",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": snapshot_data,
                }
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index1 = build_trace_index(str(trace_path))
            index2 = build_trace_index(str(trace_path))

            digest1 = index1.steps[0].snapshot_after.digest
            digest2 = index2.steps[0].snapshot_after.digest

            assert digest1 == digest2
            assert digest1.startswith("sha256:")

    def test_snapshot_digest_noise_resistance(self):
        """Small changes (2px bbox shift) should produce same digest."""
        base_snapshot = {
            "url": "https://example.com",
            "viewport": {"width": 1920, "height": 1080},
            "elements": [
                {
                    "id": 1,
                    "role": "button",
                    "text": "  Click  me  ",  # Extra whitespace
                    "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0},
                }
            ],
        }

        shifted_snapshot = {
            "url": "https://example.com",
            "viewport": {"width": 1920, "height": 1080},
            "elements": [
                {
                    "id": 1,
                    "role": "button",
                    "text": "Click me",  # No extra whitespace
                    "bbox": {
                        "x": 10.5,
                        "y": 20.5,
                        "width": 100.5,
                        "height": 50.5,
                    },  # Sub-2px shift
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            trace1_path = Path(tmpdir) / "base.jsonl"
            trace2_path = Path(tmpdir) / "shifted.jsonl"

            with open(trace1_path, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "v": 1,
                            "type": "snapshot",
                            "ts": "2025-12-29T10:00:00.000Z",
                            "step_id": "step-1",
                            "data": base_snapshot,
                        }
                    )
                    + "\n"
                )

            with open(trace2_path, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "v": 1,
                            "type": "snapshot",
                            "ts": "2025-12-29T10:00:00.000Z",
                            "step_id": "step-1",
                            "data": shifted_snapshot,
                        }
                    )
                    + "\n"
                )

            index1 = build_trace_index(str(trace1_path))
            index2 = build_trace_index(str(trace2_path))

            digest1 = index1.steps[0].snapshot_after.digest
            digest2 = index2.steps[0].snapshot_after.digest

            assert digest1 == digest2  # Should be identical despite noise

    def test_action_digest_privacy(self):
        """Typed text should not appear in action digest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "privacy-test.jsonl"

            sensitive_text = "my-secret-password"
            events = [
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {
                        "type": "TYPE",
                        "target_element_id": 15,
                        "text": sensitive_text,
                        "success": True,
                    },
                }
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            # Convert index to JSON string
            index_json = json.dumps(index.to_dict())

            # Verify sensitive text is NOT in index
            assert sensitive_text not in index_json

            # Verify action digest exists and is a hash
            action_digest = index.steps[0].action.args_digest
            assert action_digest is not None
            assert action_digest.startswith("sha256:")

    def test_synthetic_step(self):
        """Events without step_id should create step-0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "synthetic-step.jsonl"

            events = [
                {"v": 1, "type": "run_start", "ts": "2025-12-29T10:00:00.000Z", "data": {}},
                {"v": 1, "type": "action", "ts": "2025-12-29T10:00:01.000Z", "data": {}},
                {"v": 1, "type": "run_end", "ts": "2025-12-29T10:00:02.000Z", "data": {}},
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.step_count == 1
            assert len(index.steps) == 1
            assert index.steps[0].step_id == "step-0"  # Synthetic step

    def test_index_idempotency(self):
        """Regenerating index should produce identical output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "idempotent.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"type": "CLICK"},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index1 = build_trace_index(str(trace_path))
            index2 = build_trace_index(str(trace_path))

            # Compare all fields except created_at (timestamp will differ)
            assert index1.version == index2.version
            assert index1.run_id == index2.run_id
            assert index1.trace_file.sha256 == index2.trace_file.sha256
            assert index1.summary.event_count == index2.summary.event_count
            assert len(index1.steps) == len(index2.steps)

            for step1, step2 in zip(index1.steps, index2.steps):
                assert step1.step_id == step2.step_id
                assert step1.offset_start == step2.offset_start
                assert step1.offset_end == step2.offset_end

    def test_write_trace_index(self):
        """write_trace_index should create index file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "test.jsonl"

            events = [{"v": 1, "type": "run_start", "ts": "2025-12-29T10:00:00.000Z", "data": {}}]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index_path = write_trace_index(str(trace_path))

            assert os.path.exists(index_path)
            assert index_path.endswith(".index.json")

            # Verify index content
            with open(index_path) as f:
                index_data = json.load(f)

            assert index_data["version"] == 1
            assert index_data["run_id"] == "test"
            assert "summary" in index_data
            assert "steps" in index_data

    def test_error_counting(self):
        """Errors should be counted in summary and affect step status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "errors.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "error",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"message": "Something failed"},
                },
                {
                    "v": 1,
                    "type": "step_end",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {
                        "v": 1,
                        "step_id": "step-1",
                        "step_index": 1,
                        "goal": "Test goal",
                        "attempt": 0,
                        "pre": {"url": "https://example.com", "snapshot_digest": "sha256:test"},
                        "llm": {"response_text": "CLICK(42)", "response_hash": "sha256:test"},
                        "exec": {
                            "success": False,
                            "action": "click",
                            "outcome": "Action failed",
                            "duration_ms": 100,
                        },
                        "post": {"url": "https://example.com"},
                        "verify": {"passed": False, "signals": {}},
                    },
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.error_count == 1
            assert index.steps[0].status == "failure"

    def test_llm_call_counting(self):
        """LLM calls should be counted per step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "llm.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "llm_response",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "llm_response",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.steps[0].counters.llm_calls == 2

    def test_malformed_lines_skipped(self):
        """Malformed JSON lines should be skipped gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "malformed.jsonl"

            with open(trace_path, "w") as f:
                f.write('{"v": 1, "type": "run_start", "ts": "2025-12-29T10:00:00.000Z"}\n')
                f.write("this is not valid json\n")  # Malformed line
                f.write('{"v": 1, "type": "run_end", "ts": "2025-12-29T10:00:01.000Z"}\n')

            index = build_trace_index(str(trace_path))

            # Should have 2 valid events (malformed line skipped)
            assert index.summary.event_count == 2

    def test_file_not_found(self):
        """Should raise FileNotFoundError for non-existent file."""
        with pytest.raises(FileNotFoundError):
            build_trace_index("/nonexistent/trace.jsonl")

    def test_line_number_tracking(self):
        """Index should track line numbers for each step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "line-numbers.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "run_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "data": {"agent": "TestAgent", "llm_model": "gpt-4"},
                },
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"goal": "Test goal"},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {"type": "CLICK"},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            # run_start creates synthetic step-0 on line 1, step-1 has events on lines 2-3
            assert len(index.steps) >= 2
            # Find step-1 (skip synthetic step-0 from run_start)
            step1 = next(s for s in index.steps if s.step_id == "step-1")
            # line_number tracks the last event for this step (action on line 3)
            assert step1.line_number == 3
            assert index.trace_file.line_count == 3

    def test_agent_name_extraction(self):
        """Index should extract agent name from run_start event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "agent-name.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "run_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "data": {"agent": "MyTestAgent", "llm_model": "gpt-4"},
                },
                {
                    "v": 1,
                    "type": "run_end",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "data": {},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.agent_name == "MyTestAgent"

    def test_duration_calculation(self):
        """Index should calculate duration_ms from timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "duration.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "run_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "run_end",
                    "ts": "2025-12-29T10:01:30.000Z",  # 90 seconds later
                    "data": {},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.duration_ms == 90000  # 90 seconds = 90000ms

    def test_counters_aggregation(self):
        """Index should aggregate counters across all steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "counters.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "snapshot",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"url": "https://example.com"},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {"type": "CLICK"},
                },
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:03.000Z",
                    "step_id": "step-2",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "snapshot",
                    "ts": "2025-12-29T10:00:04.000Z",
                    "step_id": "step-2",
                    "data": {"url": "https://example.com"},
                },
                {
                    "v": 1,
                    "type": "action",
                    "ts": "2025-12-29T10:00:05.000Z",
                    "step_id": "step-2",
                    "data": {"type": "TYPE"},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.summary.counters is not None
            assert index.summary.counters["snapshot_count"] == 2
            assert index.summary.counters["action_count"] == 2
            assert index.summary.counters["error_count"] == 0

    def test_status_defaults_to_failure(self):
        """Steps without step_end should default to 'failure' status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "default-status.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                # No step_end event - should default to failure
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            assert index.steps[0].status == "failure"

    def test_to_frontend_dict(self):
        """to_frontend_dict should produce frontend-compatible format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "frontend-format.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "run_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "data": {"agent": "TestAgent"},
                },
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"goal": "Test goal"},
                },
                {
                    "v": 1,
                    "type": "step_end",
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {
                        "v": 1,
                        "step_id": "step-1",
                        "step_index": 1,
                        "goal": "Test goal",
                        "attempt": 0,
                        "pre": {"snapshot_digest": "sha256:test"},
                        "llm": {"response_text": "CLICK(42)", "response_hash": "sha256:test"},
                        "exec": {
                            "success": True,
                            "action": "click",
                            "outcome": "Action executed",
                            "duration_ms": 100,
                        },
                        "post": {"url": "https://example.com"},
                        "verify": {"passed": True, "signals": {}},
                    },
                },
                {
                    "v": 1,
                    "type": "run_end",
                    "ts": "2025-12-29T10:00:03.000Z",
                    "data": {"steps": 1, "status": "success"},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))
            frontend_dict = index.to_sentience_studio_dict()

            # Check field name mappings
            assert "generated_at" in frontend_dict  # Renamed from created_at
            assert "trace_file" in frontend_dict
            assert frontend_dict["trace_file"]["line_count"] == 4
            assert "summary" in frontend_dict
            assert frontend_dict["summary"]["agent_name"] == "TestAgent"
            # Includes synthetic step-0 from run_start, so total_steps is 2
            assert frontend_dict["summary"]["total_steps"] >= 1  # Renamed from step_count
            assert frontend_dict["summary"]["start_time"] is not None  # Renamed from first_ts
            assert frontend_dict["summary"]["end_time"] is not None  # Renamed from last_ts
            assert frontend_dict["summary"]["duration_ms"] > 0
            assert "counters" in frontend_dict["summary"]
            assert "steps" in frontend_dict
            # Find step-1 (skip synthetic step-0 from run_start)
            step1_dict = next(
                s for s in frontend_dict["steps"] if s.get("action", {}).get("goal") == "Test goal"
            )
            assert step1_dict["step"] >= 1  # Converted from 0-based to 1-based
            assert step1_dict["line_number"] is not None
            assert step1_dict["status"] == "success"
            assert "action" in step1_dict
            assert step1_dict["action"]["goal"] == "Test goal"  # Goal moved into action

    def test_write_trace_index_frontend_format(self):
        """write_trace_index with frontend_format=True should use frontend format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "test.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "run_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "data": {"agent": "TestAgent"},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index_path = write_trace_index(str(trace_path), frontend_format=True)

            with open(index_path) as f:
                index_data = json.load(f)

            # Check frontend format fields
            assert "generated_at" in index_data  # Frontend format
            assert "summary" in index_data
            assert "agent_name" in index_data["summary"]

    def test_event_type_backward_compatibility(self):
        """Indexer should handle both old and new event type names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "event-types.jsonl"

            events = [
                {
                    "v": 1,
                    "type": "step_start",
                    "ts": "2025-12-29T10:00:00.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
                {
                    "v": 1,
                    "type": "snapshot_taken",  # New schema name
                    "ts": "2025-12-29T10:00:01.000Z",
                    "step_id": "step-1",
                    "data": {"url": "https://example.com"},
                },
                {
                    "v": 1,
                    "type": "action_executed",  # New schema name
                    "ts": "2025-12-29T10:00:02.000Z",
                    "step_id": "step-1",
                    "data": {"type": "CLICK"},
                },
                {
                    "v": 1,
                    "type": "llm_called",  # New schema name
                    "ts": "2025-12-29T10:00:03.000Z",
                    "step_id": "step-1",
                    "data": {},
                },
            ]

            with open(trace_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            index = build_trace_index(str(trace_path))

            # Should process all events correctly
            assert index.steps[0].counters.snapshots == 1
            assert index.steps[0].counters.actions == 1
            assert index.steps[0].counters.llm_calls == 1
