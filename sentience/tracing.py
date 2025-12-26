"""
Trace event writer for Sentience agents.

Provides abstract interface and JSONL implementation for emitting trace events.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union


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
        """Close the file."""
        if hasattr(self, "_file") and not self._file.closed:
            self._file.close()

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
    """

    run_id: str
    sink: TraceSink
    seq: int = field(default=0, init=False)

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
        data = {
            "step_id": step_id,
            "step_index": step_index,
            "goal": goal,
            "attempt": attempt,
        }
        if pre_url is not None:
            data["pre_url"] = pre_url

        self.emit("step_start", data, step_id=step_id)

    def emit_run_end(self, steps: int) -> None:
        """
        Emit run_end event.

        Args:
            steps: Total number of steps executed
        """
        self.emit("run_end", {"steps": steps})

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

    def close(self) -> None:
        """Close the underlying sink."""
        self.sink.close()

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
        return False
