"""
Trace file management utilities for consistent file operations.

This module provides helper functions for common trace file operations
shared between JsonlTraceSink and CloudTraceSink.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from .models import TraceStats


class TraceFileManager:
    """
    Helper for common trace file operations.

    Provides static methods for file operations shared across trace sinks.
    """

    @staticmethod
    def write_event(file_handle: Any, event: dict[str, Any]) -> None:
        """
        Write a trace event to a file handle as JSONL.

        Args:
            file_handle: Open file handle (must be writable)
            event: Event dictionary to write
        """
        json_str = json.dumps(event, ensure_ascii=False)
        file_handle.write(json_str + "\n")
        file_handle.flush()  # Ensure written to disk

    @staticmethod
    def ensure_directory(path: Path) -> None:
        """
        Ensure the parent directory of a path exists.

        Args:
            path: File path whose parent directory should exist
        """
        path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def read_events(path: Path) -> list[dict[str, Any]]:
        """
        Read all events from a JSONL trace file.

        Args:
            path: Path to JSONL trace file

        Returns:
            List of event dictionaries

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file contains invalid JSON
        """
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    # Skip invalid lines but continue reading
                    continue
        return events

    @staticmethod
    def extract_stats(
        events: list[dict[str, Any]],
        infer_status_func: None | (
            Callable[[list[dict[str, Any]], dict[str, Any] | None], str]
        ) = None,
    ) -> TraceStats:
        """
        Extract execution statistics from trace events.

        This is a common operation shared between JsonlTraceSink and CloudTraceSink.

        Args:
            events: List of trace event dictionaries
            infer_status_func: Optional function to infer final_status from events.
                             If None, uses default inference logic.

        Returns:
            TraceStats with execution statistics
        """
        if not events:
            return TraceStats(
                total_steps=0,
                total_events=0,
                duration_ms=None,
                final_status="unknown",
                started_at=None,
                ended_at=None,
            )

        # Find run_start and run_end events
        run_start = next((e for e in events if e.get("type") == "run_start"), None)
        run_end = next((e for e in events if e.get("type") == "run_end"), None)

        # Extract timestamps
        started_at: str | None = None
        ended_at: str | None = None
        if run_start:
            started_at = run_start.get("ts")
        if run_end:
            ended_at = run_end.get("ts")

        # Calculate duration
        duration_ms: int | None = None
        if started_at and ended_at:
            try:
                from datetime import datetime

                start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                delta = end_dt - start_dt
                duration_ms = int(delta.total_seconds() * 1000)
            except Exception:
                pass

        # Count steps (from step_start events, only first attempt)
        step_indices = set()
        for event in events:
            if event.get("type") == "step_start":
                step_index = event.get("data", {}).get("step_index")
                if step_index is not None:
                    step_indices.add(step_index)
        total_steps = len(step_indices) if step_indices else 0

        # If run_end has steps count, use that (more accurate)
        if run_end:
            steps_from_end = run_end.get("data", {}).get("steps")
            if steps_from_end is not None:
                total_steps = max(total_steps, steps_from_end)

        # Count total events
        total_events = len(events)

        # Infer final status
        if infer_status_func:
            final_status = infer_status_func(events, run_end)
        else:
            final_status = TraceFileManager._infer_final_status(events, run_end)

        return TraceStats(
            total_steps=total_steps,
            total_events=total_events,
            duration_ms=duration_ms,
            final_status=final_status,
            started_at=started_at,
            ended_at=ended_at,
        )

    @staticmethod
    def _infer_final_status(
        events: list[dict[str, Any]],
        run_end: dict[str, Any] | None,
    ) -> str:
        """
        Infer final status from trace events.

        Args:
            events: List of trace event dictionaries
            run_end: Optional run_end event dictionary

        Returns:
            Final status string: "success", "failure", "partial", or "unknown"
        """
        # Check for run_end event with status
        if run_end:
            status = run_end.get("data", {}).get("status")
            if status in ("success", "failure", "partial", "unknown"):
                return status

        # Infer from error events
        has_errors = any(e.get("type") == "error" for e in events)
        if has_errors:
            step_ends = [e for e in events if e.get("type") == "step_end"]
            if step_ends:
                return "partial"
            else:
                return "failure"
        else:
            step_ends = [e for e in events if e.get("type") == "step_end"]
            if step_ends:
                return "success"
            else:
                return "unknown"
