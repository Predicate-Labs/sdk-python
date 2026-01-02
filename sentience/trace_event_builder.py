"""
Trace event building utilities for agent-based tracing.

This module provides centralized trace event building logic to reduce duplication
across agent implementations.
"""

from typing import Any, Optional

from .models import AgentActionResult, Element, Snapshot


class TraceEventBuilder:
    """
    Helper for building trace events with consistent structure.

    Provides static methods for building common trace event types:
    - snapshot_taken events
    - step_end events
    """

    @staticmethod
    def build_snapshot_event(
        snapshot: Snapshot,
        include_all_elements: bool = True,
    ) -> dict[str, Any]:
        """
        Build snapshot_taken trace event data.

        Args:
            snapshot: Snapshot to build event from
            include_all_elements: If True, include all elements (for DOM tree display).
                                 If False, use filtered elements only.

        Returns:
            Dictionary with snapshot event data
        """
        # Include ALL elements with full data for DOM tree display
        # Use snap.elements (all elements) not filtered_elements
        elements_data = [el.model_dump() for el in snapshot.elements]

        return {
            "url": snapshot.url,
            "element_count": len(snapshot.elements),
            "timestamp": snapshot.timestamp,
            "elements": elements_data,  # Full element data for DOM tree
        }

    @staticmethod
    def build_step_end_event(
        step_id: str,
        step_index: int,
        goal: str,
        attempt: int,
        pre_url: str,
        post_url: str,
        snapshot_digest: str | None,
        llm_data: dict[str, Any],
        exec_data: dict[str, Any],
        verify_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build step_end trace event data.

        Args:
            step_id: Unique step identifier
            step_index: Step index (0-based)
            goal: User's goal for this step
            attempt: Attempt number (0-based)
            pre_url: URL before action execution
            post_url: URL after action execution
            snapshot_digest: Digest of snapshot before action
            llm_data: LLM interaction data
            exec_data: Action execution data
            verify_data: Verification data

        Returns:
            Dictionary with step_end event data
        """
        return {
            "v": 1,
            "step_id": step_id,
            "step_index": step_index,
            "goal": goal,
            "attempt": attempt,
            "pre": {
                "url": pre_url,
                "snapshot_digest": snapshot_digest,
            },
            "llm": llm_data,
            "exec": exec_data,
            "post": {
                "url": post_url,
            },
            "verify": verify_data,
        }
