"""
Trace indexing module for Sentience SDK.
"""

from .indexer import build_trace_index, write_trace_index, read_step_events
from .index_schema import (
    TraceIndex,
    StepIndex,
    TraceSummary,
    TraceFileInfo,
    SnapshotInfo,
    ActionInfo,
    StepCounters,
)

__all__ = [
    "build_trace_index",
    "write_trace_index",
    "read_step_events",
    "TraceIndex",
    "StepIndex",
    "TraceSummary",
    "TraceFileInfo",
    "SnapshotInfo",
    "ActionInfo",
    "StepCounters",
]
