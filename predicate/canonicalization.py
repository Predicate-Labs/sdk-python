"""
Shared canonicalization utilities for snapshot comparison and indexing.

This module provides consistent normalization functions used by both:
- trace_indexing/indexer.py (for computing stable digests)
- snapshot_diff.py (for computing diff_status labels)

By sharing these helpers, we ensure consistent behavior:
- Same text normalization (whitespace, case, length)
- Same bbox rounding (2px precision)
- Same change detection thresholds
"""

from typing import Any


def normalize_text(text: str | None, max_len: int = 80) -> str:
    """
    Normalize text for canonical comparison.

    Transforms:
    - Trims leading/trailing whitespace
    - Collapses internal whitespace to single spaces
    - Lowercases
    - Caps length

    Args:
        text: Input text (may be None)
        max_len: Maximum length to retain (default: 80)

    Returns:
        Normalized text string (empty string if input is None)

    Examples:
        >>> normalize_text("  Hello   World  ")
        'hello world'
        >>> normalize_text(None)
        ''
    """
    if not text:
        return ""
    # Trim and collapse whitespace
    normalized = " ".join(text.split())
    # Lowercase
    normalized = normalized.lower()
    # Cap length
    if len(normalized) > max_len:
        normalized = normalized[:max_len]
    return normalized


def round_bbox(bbox: dict[str, float], precision: int = 2) -> dict[str, int]:
    """
    Round bbox coordinates to reduce noise.

    Snaps coordinates to grid of `precision` pixels to ignore
    sub-pixel rendering differences.

    Args:
        bbox: Bounding box with x, y, width, height
        precision: Grid size in pixels (default: 2)

    Returns:
        Rounded bbox with integer coordinates

    Examples:
        >>> round_bbox({"x": 101, "y": 203, "width": 50, "height": 25})
        {'x': 100, 'y': 202, 'width': 50, 'height': 24}
    """
    return {
        "x": round(bbox.get("x", 0) / precision) * precision,
        "y": round(bbox.get("y", 0) / precision) * precision,
        "width": round(bbox.get("width", 0) / precision) * precision,
        "height": round(bbox.get("height", 0) / precision) * precision,
    }


def bbox_equal(bbox1: dict[str, Any], bbox2: dict[str, Any], threshold: float = 5.0) -> bool:
    """
    Check if two bboxes are equal within a threshold.

    Args:
        bbox1: First bounding box
        bbox2: Second bounding box
        threshold: Maximum allowed difference in pixels (default: 5.0)

    Returns:
        True if all bbox properties differ by less than threshold

    Examples:
        >>> bbox_equal({"x": 100, "y": 200, "width": 50, "height": 25},
        ...            {"x": 102, "y": 200, "width": 50, "height": 25})
        True  # 2px difference is below 5px threshold
    """
    return (
        abs(bbox1.get("x", 0) - bbox2.get("x", 0)) <= threshold
        and abs(bbox1.get("y", 0) - bbox2.get("y", 0)) <= threshold
        and abs(bbox1.get("width", 0) - bbox2.get("width", 0)) <= threshold
        and abs(bbox1.get("height", 0) - bbox2.get("height", 0)) <= threshold
    )


def bbox_changed(bbox1: dict[str, Any], bbox2: dict[str, Any], threshold: float = 5.0) -> bool:
    """
    Check if two bboxes differ beyond the threshold.

    This is the inverse of bbox_equal, provided for semantic clarity
    in diff detection code.

    Args:
        bbox1: First bounding box
        bbox2: Second bounding box
        threshold: Maximum allowed difference in pixels (default: 5.0)

    Returns:
        True if any bbox property differs by more than threshold
    """
    return not bbox_equal(bbox1, bbox2, threshold)


def canonicalize_element(elem: dict[str, Any]) -> dict[str, Any]:
    """
    Create canonical representation of an element for comparison/hashing.

    Extracts and normalizes the fields that matter for identity:
    - id, role, normalized text, rounded bbox
    - is_primary, is_clickable from visual_cues

    Args:
        elem: Raw element dictionary

    Returns:
        Canonical element dictionary with normalized fields

    Examples:
        >>> canonicalize_element({
        ...     "id": 1,
        ...     "role": "button",
        ...     "text": "  Click Me  ",
        ...     "bbox": {"x": 101, "y": 200, "width": 50, "height": 25},
        ...     "visual_cues": {"is_primary": True, "is_clickable": True}
        ... })
        {'id': 1, 'role': 'button', 'text_norm': 'click me', 'bbox': {'x': 100, 'y': 200, 'width': 50, 'height': 24}, 'is_primary': True, 'is_clickable': True}
    """
    # Extract is_primary and is_clickable from visual_cues if present
    visual_cues = elem.get("visual_cues", {})
    is_primary = (
        visual_cues.get("is_primary", False)
        if isinstance(visual_cues, dict)
        else elem.get("is_primary", False)
    )
    is_clickable = (
        visual_cues.get("is_clickable", False)
        if isinstance(visual_cues, dict)
        else elem.get("is_clickable", False)
    )

    return {
        "id": elem.get("id"),
        "role": elem.get("role", ""),
        "text_norm": normalize_text(elem.get("text")),
        "bbox": round_bbox(elem.get("bbox", {"x": 0, "y": 0, "width": 0, "height": 0})),
        "is_primary": is_primary,
        "is_clickable": is_clickable,
    }


def content_equal(elem1: dict[str, Any], elem2: dict[str, Any]) -> bool:
    """
    Check if two elements have equal content (ignoring position).

    Compares normalized text, role, and visual cues.

    Args:
        elem1: First element (raw or canonical)
        elem2: Second element (raw or canonical)

    Returns:
        True if content is equal after normalization
    """
    # Normalize both elements
    c1 = canonicalize_element(elem1)
    c2 = canonicalize_element(elem2)

    return (
        c1["role"] == c2["role"]
        and c1["text_norm"] == c2["text_norm"]
        and c1["is_primary"] == c2["is_primary"]
        and c1["is_clickable"] == c2["is_clickable"]
    )


def content_changed(elem1: dict[str, Any], elem2: dict[str, Any]) -> bool:
    """
    Check if two elements have different content (ignoring position).

    This is the inverse of content_equal, provided for semantic clarity
    in diff detection code.

    Args:
        elem1: First element
        elem2: Second element

    Returns:
        True if content differs after normalization
    """
    return not content_equal(elem1, elem2)
