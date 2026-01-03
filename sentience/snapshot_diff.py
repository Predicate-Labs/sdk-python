"""
Snapshot comparison utilities for diff_status detection.

Implements change detection logic for the Diff Overlay feature.
"""

from typing import Literal

from .models import Element, Snapshot


class SnapshotDiff:
    """
    Utility for comparing snapshots and computing diff_status for elements.

    Implements the logic described in DIFF_STATUS_GAP_ANALYSIS.md:
    - ADDED: Element exists in current but not in previous
    - REMOVED: Element existed in previous but not in current
    - MODIFIED: Element exists in both but has changed
    - MOVED: Element exists in both but position changed
    """

    @staticmethod
    def _has_bbox_changed(el1: Element, el2: Element, threshold: float = 5.0) -> bool:
        """
        Check if element's bounding box has changed significantly.

        Args:
            el1: First element
            el2: Second element
            threshold: Position change threshold in pixels (default: 5.0)

        Returns:
            True if position or size changed beyond threshold
        """
        return (
            abs(el1.bbox.x - el2.bbox.x) > threshold
            or abs(el1.bbox.y - el2.bbox.y) > threshold
            or abs(el1.bbox.width - el2.bbox.width) > threshold
            or abs(el1.bbox.height - el2.bbox.height) > threshold
        )

    @staticmethod
    def _has_content_changed(el1: Element, el2: Element) -> bool:
        """
        Check if element's content has changed.

        Args:
            el1: First element
            el2: Second element

        Returns:
            True if text, role, or visual properties changed
        """
        # Compare text content
        if el1.text != el2.text:
            return True

        # Compare role
        if el1.role != el2.role:
            return True

        # Compare visual cues
        if el1.visual_cues.is_primary != el2.visual_cues.is_primary:
            return True
        if el1.visual_cues.is_clickable != el2.visual_cues.is_clickable:
            return True

        return False

    @staticmethod
    def compute_diff_status(
        current: Snapshot,
        previous: Snapshot | None,
    ) -> list[Element]:
        """
        Compare current snapshot with previous and set diff_status on elements.

        Args:
            current: Current snapshot
            previous: Previous snapshot (None if this is the first snapshot)

        Returns:
            List of elements with diff_status set (includes REMOVED elements from previous)
        """
        # If no previous snapshot, all current elements are ADDED
        if previous is None:
            result = []
            for el in current.elements:
                # Create a copy with diff_status set
                el_dict = el.model_dump()
                el_dict["diff_status"] = "ADDED"
                result.append(Element(**el_dict))
            return result

        # Build lookup maps by element ID
        current_by_id = {el.id: el for el in current.elements}
        previous_by_id = {el.id: el for el in previous.elements}

        current_ids = set(current_by_id.keys())
        previous_ids = set(previous_by_id.keys())

        result: list[Element] = []

        # Process current elements
        for el in current.elements:
            el_dict = el.model_dump()

            if el.id not in previous_ids:
                # Element is new - mark as ADDED
                el_dict["diff_status"] = "ADDED"
            else:
                # Element existed before - check for changes
                prev_el = previous_by_id[el.id]

                bbox_changed = SnapshotDiff._has_bbox_changed(el, prev_el)
                content_changed = SnapshotDiff._has_content_changed(el, prev_el)

                if bbox_changed and content_changed:
                    # Both position and content changed - mark as MODIFIED
                    el_dict["diff_status"] = "MODIFIED"
                elif bbox_changed:
                    # Only position changed - mark as MOVED
                    el_dict["diff_status"] = "MOVED"
                elif content_changed:
                    # Only content changed - mark as MODIFIED
                    el_dict["diff_status"] = "MODIFIED"
                else:
                    # No change - don't set diff_status (frontend expects undefined)
                    el_dict["diff_status"] = None

            result.append(Element(**el_dict))

        # Process removed elements (existed in previous but not in current)
        for prev_id in previous_ids - current_ids:
            prev_el = previous_by_id[prev_id]
            el_dict = prev_el.model_dump()
            el_dict["diff_status"] = "REMOVED"
            result.append(Element(**el_dict))

        return result
