"""
Snapshot comparison utilities for diff_status detection.

Implements change detection logic for the Diff Overlay feature.

Uses shared canonicalization helpers from canonicalization.py to ensure
consistent comparison behavior with trace_indexing/indexer.py.
"""

from .canonicalization import bbox_changed, content_changed
from .models import Element, Snapshot


class SnapshotDiff:
    """
    Utility for comparing snapshots and computing diff_status for elements.

    Implements the logic described in DIFF_STATUS_GAP_ANALYSIS.md:
    - ADDED: Element exists in current but not in previous
    - REMOVED: Element existed in previous but not in current
    - MODIFIED: Element exists in both but has changed
    - MOVED: Element exists in both but position changed

    Uses canonicalized comparisons (normalized text, rounded bbox) to reduce
    noise from insignificant changes like sub-pixel rendering differences
    or whitespace variations.
    """

    @staticmethod
    def _element_to_dict(el: Element) -> dict:
        """Convert Element model to dict for canonicalization helpers."""
        return {
            "id": el.id,
            "role": el.role,
            "text": el.text,
            "bbox": {
                "x": el.bbox.x,
                "y": el.bbox.y,
                "width": el.bbox.width,
                "height": el.bbox.height,
            },
            "visual_cues": {
                "is_primary": el.visual_cues.is_primary,
                "is_clickable": el.visual_cues.is_clickable,
            },
        }

    @staticmethod
    def compute_diff_status(
        current: Snapshot,
        previous: Snapshot | None,
    ) -> list[Element]:
        """
        Compare current snapshot with previous and set diff_status on elements.

        Uses canonicalized comparisons:
        - Text is normalized (trimmed, collapsed whitespace, lowercased)
        - Bbox is rounded to 2px grid to ignore sub-pixel differences

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
                # Element existed before - check for changes using canonicalized comparisons
                prev_el = previous_by_id[el.id]

                # Convert to dicts for canonicalization helpers
                el_data = SnapshotDiff._element_to_dict(el)
                prev_el_data = SnapshotDiff._element_to_dict(prev_el)

                has_bbox_changed = bbox_changed(el_data["bbox"], prev_el_data["bbox"])
                has_content_changed = content_changed(el_data, prev_el_data)

                if has_bbox_changed and has_content_changed:
                    # Both position and content changed - mark as MODIFIED
                    el_dict["diff_status"] = "MODIFIED"
                elif has_bbox_changed:
                    # Only position changed - mark as MOVED
                    el_dict["diff_status"] = "MOVED"
                elif has_content_changed:
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
