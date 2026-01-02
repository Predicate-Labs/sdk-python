"""
Tests for TraceFileManager helper class.
"""

import json
import tempfile
from pathlib import Path

import pytest

from sentience.trace_file_manager import TraceFileManager


class TestTraceFileManager:
    """Test TraceFileManager helper methods"""

    def test_write_event(self):
        """Test writing event to file handle"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            temp_path = Path(f.name)

        try:
            with open(temp_path, "w", encoding="utf-8") as file_handle:
                event = {"type": "test", "data": {"key": "value"}}
                TraceFileManager.write_event(file_handle, event)

            # Read back and verify
            with open(temp_path, encoding="utf-8") as f:
                line = f.read().strip()
                assert line
                parsed = json.loads(line)
                assert parsed == event
        finally:
            temp_path.unlink()

    def test_ensure_directory(self):
        """Test ensuring directory exists"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "nested" / "path" / "file.jsonl"
            TraceFileManager.ensure_directory(test_path)

            assert test_path.parent.exists()
            assert test_path.parent.is_dir()

    def test_read_events(self):
        """Test reading events from JSONL file"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            temp_path = Path(f.name)

        try:
            # Write test events
            events = [
                {"type": "event1", "data": {"key1": "value1"}},
                {"type": "event2", "data": {"key2": "value2"}},
                {"type": "event3", "data": {"key3": "value3"}},
            ]

            with open(temp_path, "w", encoding="utf-8") as f:
                for event in events:
                    TraceFileManager.write_event(f, event)

            # Read back
            read_events = TraceFileManager.read_events(temp_path)

            assert len(read_events) == 3
            assert read_events == events
        finally:
            temp_path.unlink()

    def test_read_events_skips_empty_lines(self):
        """Test that empty lines are skipped when reading"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            temp_path = Path(f.name)

        try:
            # Write events with empty lines
            with open(temp_path, "w", encoding="utf-8") as f:
                TraceFileManager.write_event(f, {"type": "event1"})
                f.write("\n")  # Empty line
                f.write("  \n")  # Whitespace-only line
                TraceFileManager.write_event(f, {"type": "event2"})

            read_events = TraceFileManager.read_events(temp_path)

            assert len(read_events) == 2
            assert read_events[0]["type"] == "event1"
            assert read_events[1]["type"] == "event2"
        finally:
            temp_path.unlink()

    def test_read_events_handles_invalid_json(self):
        """Test that invalid JSON lines are skipped"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            temp_path = Path(f.name)

        try:
            # Write valid and invalid events
            with open(temp_path, "w", encoding="utf-8") as f:
                TraceFileManager.write_event(f, {"type": "event1"})
                f.write("invalid json line\n")
                TraceFileManager.write_event(f, {"type": "event2"})

            read_events = TraceFileManager.read_events(temp_path)

            assert len(read_events) == 2
            assert read_events[0]["type"] == "event1"
            assert read_events[1]["type"] == "event2"
        finally:
            temp_path.unlink()

    def test_read_events_file_not_found(self):
        """Test that FileNotFoundError is raised for non-existent file"""
        with pytest.raises(FileNotFoundError):
            TraceFileManager.read_events(Path("/nonexistent/file.jsonl"))

