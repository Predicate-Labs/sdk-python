"""
Trace event writer for Sentience agents.

Provides abstract interface and JSONL implementation for emitting trace events.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .models import TraceStats


@dataclass
class TraceEvent:
    """
    Trace event data structure.

    Represents a single event in the agent execution trace.
    """

    v: int  # Schema version
    type: str  # Event type
    ts: str  # ISO 8601 timestamp
    run_id: str  # UUID for the run
    seq: int  # Sequence number
    data: dict[str, Any]  # Event payload
    step_id: str | None = None  # UUID for the step (if step-scoped)
    ts_ms: int | None = None  # Unix timestamp in milliseconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "v": self.v,
            "type": self.type,
            "ts": self.ts,
            "run_id": self.run_id,
            "seq": self.seq,
            "data": self.data,
        }

        if self.step_id is not None:
            result["step_id"] = self.step_id

        if self.ts_ms is not None:
            result["ts_ms"] = self.ts_ms

        return result


class TraceSink(ABC):
    """
    Abstract interface for trace event sink.

    Implementations can write to files, databases, or remote services.
    """

    @abstractmethod
    def emit(self, event: dict[str, Any]) -> None:
        """
        Emit a trace event.

        Args:
            event: Event dictionary (from TraceEvent.to_dict())
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the sink and flush any buffered data."""
        pass


class JsonlTraceSink(TraceSink):
    """
    JSONL file sink for trace events.

    Writes one JSON object per line to a file.
    """

    def __init__(self, path: str | Path):
        """
        Initialize JSONL sink.

        Args:
            path: File path to write traces to
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode with line buffering
        self._file = open(self.path, "a", encoding="utf-8", buffering=1)

    def emit(self, event: dict[str, Any]) -> None:
        """
        Emit event as JSONL line.

        Args:
            event: Event dictionary
        """
        json_str = json.dumps(event, ensure_ascii=False)
        self._file.write(json_str + "\n")

    def close(self) -> None:
        """Close the file and generate index."""
        if hasattr(self, "_file") and not self._file.closed:
            self._file.close()

        # Generate index after closing file
        self._generate_index()

    def get_stats(self) -> TraceStats:
        """
        Extract execution statistics from trace file (for local traces).

        Returns:
            TraceStats with execution statistics
        """
        try:
            # Read trace file to extract stats
            with open(self.path, encoding="utf-8") as f:
                events = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        continue

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
            final_status = "unknown"
            # Check for run_end event with status
            if run_end:
                status = run_end.get("data", {}).get("status")
                if status in ("success", "failure", "partial", "unknown"):
                    final_status = status
            else:
                # Infer from error events
                has_errors = any(e.get("type") == "error" for e in events)
                if has_errors:
                    step_ends = [e for e in events if e.get("type") == "step_end"]
                    if step_ends:
                        final_status = "partial"
                    else:
                        final_status = "failure"
                else:
                    step_ends = [e for e in events if e.get("type") == "step_end"]
                    if step_ends:
                        final_status = "success"

            return TraceStats(
                total_steps=total_steps,
                total_events=total_events,
                duration_ms=duration_ms,
                final_status=final_status,
                started_at=started_at,
                ended_at=ended_at,
            )

        except Exception:
            return TraceStats(
                total_steps=0,
                total_events=0,
                duration_ms=None,
                final_status="unknown",
                started_at=None,
                ended_at=None,
            )

    def _generate_index(self) -> None:
        """Generate trace index file (automatic on close)."""
        try:
            from .trace_indexing import write_trace_index

            # Use frontend format to ensure 'step' field is present (1-based)
            # Frontend derives sequence from step.step - 1, so step must be valid
            index_path = Path(self.path).with_suffix(".index.json")
            write_trace_index(str(self.path), str(index_path), frontend_format=True)
        except Exception as e:
            # Non-fatal: log but don't crash
            print(f"⚠️  Failed to generate trace index: {e}")

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
        return False


@dataclass
class Tracer:
    """
    Trace event builder and emitter.

    Manages sequence numbers and provides convenient methods for emitting events.
    Tracks execution statistics and final status for trace completion.
    """

    run_id: str
    sink: TraceSink
    seq: int = field(default=0, init=False)
    # Stats tracking
    total_steps: int = field(default=0, init=False)
    total_events: int = field(default=0, init=False)
    started_at: datetime | None = field(default=None, init=False)
    ended_at: datetime | None = field(default=None, init=False)
    final_status: str = field(default="unknown", init=False)
    # Track step outcomes for automatic status inference
    _step_successes: int = field(default=0, init=False)
    _step_failures: int = field(default=0, init=False)
    _has_errors: bool = field(default=False, init=False)

    def emit(
        self,
        event_type: str,
        data: dict[str, Any],
        step_id: str | None = None,
    ) -> None:
        """
        Emit a trace event.

        Args:
            event_type: Type of event (e.g., 'run_start', 'step_end')
            data: Event-specific payload
            step_id: Step UUID (if step-scoped event)
        """
        self.seq += 1
        self.total_events += 1

        # Generate timestamps
        ts_ms = int(time.time() * 1000)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

        event = TraceEvent(
            v=1,
            type=event_type,
            ts=ts,
            ts_ms=ts_ms,
            run_id=self.run_id,
            seq=self.seq,
            step_id=step_id,
            data=data,
        )

        self.sink.emit(event.to_dict())

        # Track step outcomes for automatic status inference
        if event_type == "step_end":
            success = data.get("success", False)
            if success:
                self._step_successes += 1
            else:
                self._step_failures += 1
        elif event_type == "error":
            self._has_errors = True

    def emit_run_start(
        self,
        agent: str,
        llm_model: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """
        Emit run_start event.

        Args:
            agent: Agent name (e.g., 'SentienceAgent')
            llm_model: LLM model name
            config: Agent configuration
        """
        # Track start time
        self.started_at = datetime.utcnow()

        data: dict[str, Any] = {"agent": agent}
        if llm_model is not None:
            data["llm_model"] = llm_model
        if config is not None:
            data["config"] = config

        self.emit("run_start", data)

    def emit_step_start(
        self,
        step_id: str,
        step_index: int,
        goal: str,
        attempt: int = 0,
        pre_url: str | None = None,
    ) -> None:
        """
        Emit step_start event.

        Args:
            step_id: Step UUID
            step_index: Step number (1-indexed)
            goal: Step goal description
            attempt: Attempt number (0-indexed)
            pre_url: URL before step
        """
        # Track step count (only count first attempt of each step)
        if attempt == 0:
            self.total_steps = max(self.total_steps, step_index)

        data = {
            "step_id": step_id,
            "step_index": step_index,
            "goal": goal,
            "attempt": attempt,
        }
        if pre_url is not None:
            data["pre_url"] = pre_url

        self.emit("step_start", data, step_id=step_id)

    def emit_run_end(self, steps: int, status: str | None = None) -> None:
        """
        Emit run_end event.

        Args:
            steps: Total number of steps executed
            status: Optional final status ("success", "failure", "partial", "unknown")
                    If not provided, infers from tracked outcomes or uses self.final_status
        """
        # Track end time
        self.ended_at = datetime.utcnow()

        # Auto-infer status if not provided and not explicitly set
        if status is None and self.final_status == "unknown":
            self._infer_final_status()

        # Use provided status or fallback to self.final_status
        final_status = status if status is not None else self.final_status

        # Ensure total_steps is at least the provided steps value
        self.total_steps = max(self.total_steps, steps)

        self.emit("run_end", {"steps": steps, "status": final_status})

    def emit_error(
        self,
        step_id: str,
        error: str,
        attempt: int = 0,
    ) -> None:
        """
        Emit error event.

        Args:
            step_id: Step UUID
            error: Error message
            attempt: Attempt number when error occurred
        """
        data = {
            "step_id": step_id,
            "error": error,
            "attempt": attempt,
        }
        self.emit("error", data, step_id=step_id)

    def set_final_status(self, status: str) -> None:
        """
        Set the final status of the trace run.

        Args:
            status: Final status ("success", "failure", "partial", "unknown")
        """
        if status not in ("success", "failure", "partial", "unknown"):
            raise ValueError(
                f"Invalid status: {status}. Must be one of: success, failure, partial, unknown"
            )
        self.final_status = status

    def get_stats(self) -> TraceStats:
        """
        Get execution statistics for trace completion.

        Returns:
            TraceStats with execution statistics
        """
        duration_ms: int | None = None
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            duration_ms = int(delta.total_seconds() * 1000)

        return TraceStats(
            total_steps=self.total_steps,
            total_events=self.total_events,
            duration_ms=duration_ms,
            final_status=self.final_status,
            started_at=self.started_at.isoformat() + "Z" if self.started_at else None,
            ended_at=self.ended_at.isoformat() + "Z" if self.ended_at else None,
        )

    def _infer_final_status(self) -> None:
        """
        Automatically infer final_status from tracked step outcomes if not explicitly set.

        This is called automatically in close() if final_status is still "unknown".
        """
        if self.final_status != "unknown":
            # Status already set explicitly, don't override
            return

        # Infer from tracked outcomes
        if self._has_errors:
            # Has errors - check if there were successful steps too
            if self._step_successes > 0:
                self.final_status = "partial"
            else:
                self.final_status = "failure"
        elif self._step_successes > 0:
            # Has successful steps and no errors
            self.final_status = "success"
        # Otherwise stays "unknown" (no steps executed or no clear outcome)

    def close(self, **kwargs) -> None:
        """
        Close the underlying sink.

        Args:
            **kwargs: Passed through to sink.close() (e.g., blocking=True for CloudTraceSink)
        """
        # Auto-infer final_status if not explicitly set and we have step outcomes
        if self.final_status == "unknown" and (
            self._step_successes > 0 or self._step_failures > 0 or self._has_errors
        ):
            self._infer_final_status()

        # Check if sink.close() accepts kwargs (CloudTraceSink does, JsonlTraceSink doesn't)
        import inspect

        sig = inspect.signature(self.sink.close)
        if any(
            p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            for p in sig.parameters.values()
        ):
            self.sink.close(**kwargs)
        else:
            self.sink.close()

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
        return False
