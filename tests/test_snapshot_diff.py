"""
Tests for snapshot diff functionality (diff_status detection).
"""

import pytest

from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues
from sentience.snapshot_diff import SnapshotDiff


def create_element(
    element_id: int,
    role: str = "button",
    text: str | None = "Test",
    x: float = 100.0,
    y: float = 100.0,
    width: float = 50.0,
    height: float = 20.0,
) -> Element:
    """Helper to create test elements."""
    return Element(
        id=element_id,
        role=role,
        text=text,
        importance=500,
        bbox=BBox(x=x, y=y, width=width, height=height),
        visual_cues=VisualCues(is_primary=False, is_clickable=True),
    )


def create_snapshot(elements: list[Element], url: str = "http://example.com") -> Snapshot:
    """Helper to create test snapshots."""
    return Snapshot(
        status="success",
        url=url,
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
    )


def test_first_snapshot_all_added():
    """First snapshot should mark all elements as ADDED."""
    elements = [
        create_element(1, text="Button 1"),
        create_element(2, text="Button 2"),
    ]
    current = create_snapshot(elements)

    result = SnapshotDiff.compute_diff_status(current, None)

    assert len(result) == 2
    assert all(el.diff_status == "ADDED" for el in result)


def test_unchanged_elements_no_diff_status():
    """Unchanged elements should not have diff_status set."""
    elements = [create_element(1, text="Button 1")]
    previous = create_snapshot(elements)
    current = create_snapshot(elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    assert len(result) == 1
    assert result[0].diff_status is None


def test_new_element_marked_added():
    """New elements should be marked as ADDED."""
    previous_elements = [create_element(1, text="Button 1")]
    current_elements = [
        create_element(1, text="Button 1"),
        create_element(2, text="Button 2"),  # New element
    ]

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    # Find the new element
    new_element = next(el for el in result if el.id == 2)
    assert new_element.diff_status == "ADDED"

    # Existing element should have no diff_status
    existing_element = next(el for el in result if el.id == 1)
    assert existing_element.diff_status is None


def test_removed_element_marked_removed():
    """Removed elements should be included in result with REMOVED status."""
    previous_elements = [
        create_element(1, text="Button 1"),
        create_element(2, text="Button 2"),
    ]
    current_elements = [create_element(1, text="Button 1")]

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    # Should include both current element and removed element
    assert len(result) == 2

    # Find the removed element
    removed_element = next(el for el in result if el.id == 2)
    assert removed_element.diff_status == "REMOVED"


def test_moved_element_marked_moved():
    """Elements that changed position should be marked as MOVED."""
    previous_elements = [create_element(1, x=100.0, y=100.0)]
    current_elements = [create_element(1, x=200.0, y=100.0)]  # Moved 100px right

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    assert len(result) == 1
    assert result[0].diff_status == "MOVED"


def test_content_changed_marked_modified():
    """Elements that changed content should be marked as MODIFIED."""
    previous_elements = [create_element(1, text="Old Text")]
    current_elements = [create_element(1, text="New Text")]

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    assert len(result) == 1
    assert result[0].diff_status == "MODIFIED"


def test_role_changed_marked_modified():
    """Elements that changed role should be marked as MODIFIED."""
    previous_elements = [create_element(1, role="button")]
    current_elements = [create_element(1, role="link")]

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    assert len(result) == 1
    assert result[0].diff_status == "MODIFIED"


def test_both_position_and_content_changed_marked_modified():
    """Elements with both position and content changes should be marked as MODIFIED."""
    previous_elements = [create_element(1, text="Old", x=100.0)]
    current_elements = [create_element(1, text="New", x=200.0)]

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    assert len(result) == 1
    assert result[0].diff_status == "MODIFIED"


def test_small_position_change_not_detected():
    """Small position changes below threshold should not be detected."""
    previous_elements = [create_element(1, x=100.0, y=100.0)]
    current_elements = [create_element(1, x=102.0, y=102.0)]  # Moved 2px (< 5px threshold)

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    assert len(result) == 1
    assert result[0].diff_status is None  # No change detected


def test_complex_scenario():
    """Test complex scenario with multiple types of changes."""
    previous_elements = [
        create_element(1, text="Unchanged"),
        create_element(2, text="Will be removed"),
        create_element(3, text="Old text"),
        create_element(4, x=100.0),
    ]

    current_elements = [
        create_element(1, text="Unchanged"),
        # Element 2 removed
        create_element(3, text="New text"),  # Modified
        create_element(4, x=200.0),  # Moved
        create_element(5, text="New element"),  # Added
    ]

    previous = create_snapshot(previous_elements)
    current = create_snapshot(current_elements)

    result = SnapshotDiff.compute_diff_status(current, previous)

    # Should have 5 elements (4 current + 1 removed)
    assert len(result) == 5

    # Check each element
    el1 = next(el for el in result if el.id == 1)
    assert el1.diff_status is None  # Unchanged

    el2 = next(el for el in result if el.id == 2)
    assert el2.diff_status == "REMOVED"

    el3 = next(el for el in result if el.id == 3)
    assert el3.diff_status == "MODIFIED"

    el4 = next(el for el in result if el.id == 4)
    assert el4.diff_status == "MOVED"

    el5 = next(el for el in result if el.id == 5)
    assert el5.diff_status == "ADDED"
