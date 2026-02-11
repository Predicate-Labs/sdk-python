"""
Type definitions for trace index schema using concrete classes.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Literal, Optional


@dataclass
class TraceFileInfo:
    """Metadata about the trace file."""

    path: str
    size_bytes: int
    sha256: str
    line_count: int | None = None  # Number of lines in the trace file

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TraceSummary:
    """High-level summary of the trace."""

    first_ts: str
    last_ts: str
    event_count: int
    step_count: int
    error_count: int
    final_url: str | None
    status: Literal["success", "failure", "partial", "unknown"] | None = None
    agent_name: str | None = None  # Agent name from run_start event
    duration_ms: int | None = None  # Calculated duration in milliseconds
    counters: dict[str, int] | None = (
        None  # Aggregated counters (snapshot_count, action_count, error_count)
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SnapshotInfo:
    """Snapshot metadata for index."""

    snapshot_id: str | None = None
    digest: str | None = None
    url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionInfo:
    """Action metadata for index."""

    type: str | None = None
    target_element_id: int | None = None
    args_digest: str | None = None
    success: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StepCounters:
    """Event counters per step."""

    events: int = 0
    snapshots: int = 0
    actions: int = 0
    llm_calls: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StepIndex:
    """Index entry for a single step."""

    step_index: int
    step_id: str
    goal: str | None
    status: Literal["success", "failure", "partial", "unknown"]
    ts_start: str
    ts_end: str
    offset_start: int
    offset_end: int
    line_number: int | None = None  # Line number for byte-range fetching
    url_before: str | None = None
    url_after: str | None = None
    snapshot_before: SnapshotInfo = field(default_factory=SnapshotInfo)
    snapshot_after: SnapshotInfo = field(default_factory=SnapshotInfo)
    action: ActionInfo = field(default_factory=ActionInfo)
    counters: StepCounters = field(default_factory=StepCounters)

    def to_dict(self) -> dict:
        result = asdict(self)
        return result


@dataclass
class TraceIndex:
    """Complete trace index schema."""

    version: int
    run_id: str
    created_at: str
    trace_file: TraceFileInfo
    summary: TraceSummary
    steps: list[StepIndex] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_sentience_studio_dict(self) -> dict:
        """
        Convert to SS-compatible format.

        Maps SDK field names to frontend expectations:
        - created_at -> generated_at
        - first_ts -> start_time
        - last_ts -> end_time
        - step_index (0-based) -> step (1-based)
        - ts_start -> timestamp
        - Filters out "unknown" status
        """
        from datetime import datetime

        # Calculate duration if not already set
        duration_ms = self.summary.duration_ms
        if duration_ms is None and self.summary.first_ts and self.summary.last_ts:
            try:
                start = datetime.fromisoformat(self.summary.first_ts.replace("Z", "+00:00"))
                end = datetime.fromisoformat(self.summary.last_ts.replace("Z", "+00:00"))
                duration_ms = int((end - start).total_seconds() * 1000)
            except (ValueError, AttributeError):
                duration_ms = None

        # Aggregate counters if not already set
        counters = self.summary.counters
        if counters is None:
            snapshot_count = sum(step.counters.snapshots for step in self.steps)
            action_count = sum(step.counters.actions for step in self.steps)
            counters = {
                "snapshot_count": snapshot_count,
                "action_count": action_count,
                "error_count": self.summary.error_count,
            }

        return {
            "version": self.version,
            "run_id": self.run_id,
            "generated_at": self.created_at,  # Renamed from created_at
            "trace_file": {
                "path": self.trace_file.path,
                "size_bytes": self.trace_file.size_bytes,
                "line_count": self.trace_file.line_count,  # Added
            },
            "summary": {
                "agent_name": self.summary.agent_name,  # Added
                "total_steps": self.summary.step_count,  # Renamed from step_count
                "status": (
                    self.summary.status if self.summary.status != "unknown" else None
                ),  # Filter out unknown
                "start_time": self.summary.first_ts,  # Renamed from first_ts
                "end_time": self.summary.last_ts,  # Renamed from last_ts
                "duration_ms": duration_ms,  # Added
                "counters": counters,  # Added
            },
            "steps": [
                {
                    "step": s.step_index + 1,  # Convert 0-based to 1-based
                    "byte_offset": s.offset_start,
                    "line_number": s.line_number,  # Added
                    "timestamp": s.ts_start,  # Use start time
                    "action": {
                        "type": s.action.type or "",
                        "goal": s.goal,  # Move goal into action
                        "digest": s.action.args_digest,
                    },
                    "snapshot": (
                        {
                            "url": s.snapshot_after.url,
                            "digest": s.snapshot_after.digest,
                        }
                        if s.snapshot_after.url
                        else None
                    ),
                    "status": s.status if s.status != "unknown" else None,  # Filter out unknown
                }
                for s in self.steps
            ],
        }
