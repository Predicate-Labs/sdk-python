"""
Tests for importance_score normalization in trace events.
"""

import pytest

from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues
from sentience.trace_event_builder import TraceEventBuilder


def create_element(element_id: int, importance: int) -> Element:
    """Helper to create test elements with specific importance values."""
    return Element(
        id=element_id,
        role="button",
        text=f"Element {element_id}",
        importance=importance,
        bbox=BBox(x=0, y=0, width=100, height=50),
        visual_cues=VisualCues(is_primary=False, is_clickable=True),
    )


def create_snapshot(elements: list[Element]) -> Snapshot:
    """Helper to create test snapshots."""
    return Snapshot(
        status="success",
        url="http://example.com",
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
    )


def test_importance_score_normalization_basic():
    """Test basic importance score normalization to [0, 1] range."""
    elements = [
        create_element(1, importance=0),  # Min -> 0.0
        create_element(2, importance=500),  # Mid -> 0.5
        create_element(3, importance=1000),  # Max -> 1.0
    ]
    snapshot = create_snapshot(elements)

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    assert len(event_data["elements"]) == 3

    # Check normalization
    el1 = event_data["elements"][0]
    el2 = event_data["elements"][1]
    el3 = event_data["elements"][2]

    assert "importance_score" in el1
    assert "importance_score" in el2
    assert "importance_score" in el3

    assert el1["importance_score"] == 0.0  # (0 - 0) / (1000 - 0) = 0.0
    assert el2["importance_score"] == 0.5  # (500 - 0) / (1000 - 0) = 0.5
    assert el3["importance_score"] == 1.0  # (1000 - 0) / (1000 - 0) = 1.0


def test_importance_score_with_negative_values():
    """Test normalization with negative importance values."""
    elements = [
        create_element(1, importance=-300),  # Min -> 0.0
        create_element(2, importance=500),  # Mid -> ~0.44
        create_element(3, importance=1800),  # Max -> 1.0
    ]
    snapshot = create_snapshot(elements)

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    el1 = event_data["elements"][0]
    el2 = event_data["elements"][1]
    el3 = event_data["elements"][2]

    # Range: 1800 - (-300) = 2100
    assert el1["importance_score"] == 0.0
    assert abs(el2["importance_score"] - 0.380952) < 0.001  # (500 - (-300)) / 2100 ≈ 0.38
    assert el3["importance_score"] == 1.0


def test_importance_score_all_same_values():
    """Test normalization when all elements have same importance."""
    elements = [
        create_element(1, importance=500),
        create_element(2, importance=500),
        create_element(3, importance=500),
    ]
    snapshot = create_snapshot(elements)

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    # When all have same importance, should default to 0.5
    for el_data in event_data["elements"]:
        assert el_data["importance_score"] == 0.5


def test_importance_score_single_element():
    """Test normalization with single element."""
    elements = [create_element(1, importance=500)]
    snapshot = create_snapshot(elements)

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    # Single element with no range should get 0.5
    assert event_data["elements"][0]["importance_score"] == 0.5


def test_importance_score_empty_snapshot():
    """Test normalization with empty snapshot."""
    snapshot = create_snapshot([])

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    assert event_data["elements"] == []
    assert event_data["element_count"] == 0


def test_importance_score_preserves_original_importance():
    """Test that original importance field is preserved."""
    elements = [
        create_element(1, importance=100),
        create_element(2, importance=900),
    ]
    snapshot = create_snapshot(elements)

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    # Original importance should still be present
    assert event_data["elements"][0]["importance"] == 100
    assert event_data["elements"][1]["importance"] == 900

    # And importance_score should be added
    assert event_data["elements"][0]["importance_score"] == 0.0
    assert event_data["elements"][1]["importance_score"] == 1.0


def test_importance_score_in_range_0_to_1():
    """Test that all normalized scores are in [0, 1] range."""
    # Create elements with various importance values
    elements = [create_element(i, importance=i * 100 - 300) for i in range(20)]
    snapshot = create_snapshot(elements)

    event_data = TraceEventBuilder.build_snapshot_event(snapshot)

    for el_data in event_data["elements"]:
        score = el_data["importance_score"]
        assert 0.0 <= score <= 1.0, f"Score {score} not in [0, 1] range"
