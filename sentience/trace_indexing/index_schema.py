"""
Type definitions for trace index schema using concrete classes.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Literal


@dataclass
class TraceFileInfo:
    """Metadata about the trace file."""

    path: str
    size_bytes: int
    sha256: str

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
    final_url: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SnapshotInfo:
    """Snapshot metadata for index."""

    snapshot_id: Optional[str] = None
    digest: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionInfo:
    """Action metadata for index."""

    type: Optional[str] = None
    target_element_id: Optional[int] = None
    args_digest: Optional[str] = None
    success: Optional[bool] = None

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
    goal: Optional[str]
    status: Literal["ok", "error", "partial"]
    ts_start: str
    ts_end: str
    offset_start: int
    offset_end: int
    url_before: Optional[str]
    url_after: Optional[str]
    snapshot_before: SnapshotInfo
    snapshot_after: SnapshotInfo
    action: ActionInfo
    counters: StepCounters

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
    steps: List[StepIndex] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
