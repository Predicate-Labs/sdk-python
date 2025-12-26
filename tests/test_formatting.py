"""Tests for sentience.formatting module"""

from sentience.formatting import format_snapshot_for_llm
from sentience.models import BBox, Element, Snapshot, VisualCues


def test_format_snapshot_basic():
    """Test basic snapshot formatting."""
    elements = [
        Element(
            id=1,
            role="button",
            text="Sign In",
            bbox=BBox(x=100, y=50, width=80, height=30),
            visual_cues=VisualCues(is_primary=True, is_clickable=True),
            importance=10,
        ),
        Element(
            id=2,
            role="input",
            text="Email address",
            bbox=BBox(x=100, y=100, width=200, height=25),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=8,
        ),
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot, limit=10)

    # Should contain element IDs
    assert "[1]" in result
    assert "[2]" in result

    # Should contain roles
    assert "<button>" in result
    assert "<input>" in result

    # Should contain text
    assert "Sign In" in result
    assert "Email address" in result

    # Should contain visual cues
    assert "PRIMARY" in result
    assert "CLICKABLE" in result

    # Should contain positions
    assert "@ (100,50)" in result
    assert "@ (100,100)" in result

    # Should contain importance scores
    assert "(Imp:10)" in result
    assert "(Imp:8)" in result


def test_format_snapshot_limit():
    """Test that limit parameter works."""
    elements = [
        Element(
            id=i,
            role="button",
            text=f"Button {i}",
            bbox=BBox(x=0, y=0, width=10, height=10),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=5,
        )
        for i in range(1, 101)
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)

    # With limit=10, should only see first 10 elements
    result = format_snapshot_for_llm(snapshot, limit=10)
    lines = result.split("\n")
    assert len(lines) == 10
    assert "[1]" in result
    assert "[10]" in result
    assert "[11]" not in result


def test_format_snapshot_text_truncation():
    """Test that long text is truncated."""
    long_text = "a" * 100
    elements = [
        Element(
            id=1,
            role="div",
            text=long_text,
            bbox=BBox(x=0, y=0, width=10, height=10),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=5,
        ),
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot)

    # Should contain truncated text with ellipsis
    assert "..." in result
    # Should not contain full text
    assert long_text not in result


def test_format_snapshot_empty_text():
    """Test formatting with empty text."""
    elements = [
        Element(
            id=1,
            role="div",
            text="",
            bbox=BBox(x=0, y=0, width=10, height=10),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=5,
        ),
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot)

    # Should still format element
    assert "[1]" in result
    assert "<div>" in result
    assert '""' in result  # Empty quotes


def test_format_snapshot_no_visual_cues():
    """Test formatting without visual cues."""
    elements = [
        Element(
            id=1,
            role="div",
            text="Test",
            bbox=BBox(x=0, y=0, width=10, height=10),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=5,
        ),
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot)

    # Should not contain visual cues
    assert "PRIMARY" not in result
    assert "CLICKABLE" not in result
    # But should still format other fields
    assert "[1]" in result
    assert "Test" in result


def test_format_snapshot_multiple_visual_cues():
    """Test formatting with multiple visual cues."""
    elements = [
        Element(
            id=1,
            role="button",
            text="Submit",
            bbox=BBox(x=0, y=0, width=10, height=10),
            visual_cues=VisualCues(is_primary=True, is_clickable=True),
            importance=10,
        ),
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot)

    # Should contain both cues
    assert "PRIMARY" in result
    assert "CLICKABLE" in result
    # Should be comma-separated
    assert "{PRIMARY,CLICKABLE}" in result or "{CLICKABLE,PRIMARY}" in result


def test_format_snapshot_position_formatting():
    """Test that positions are formatted as integers."""
    elements = [
        Element(
            id=1,
            role="button",
            text="Test",
            bbox=BBox(x=123.7, y=456.2, width=78, height=90),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=5,
        ),
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot)

    # Should round to integers
    assert "@ (123,456)" in result


def test_format_snapshot_default_limit():
    """Test that default limit is 50."""
    elements = [
        Element(
            id=i,
            role="button",
            text=f"Button {i}",
            bbox=BBox(x=0, y=0, width=10, height=10),
            visual_cues=VisualCues(is_primary=False, is_clickable=False),
            importance=5,
        )
        for i in range(1, 101)
    ]

    snapshot = Snapshot(status="success", url="https://example.com", elements=elements)
    result = format_snapshot_for_llm(snapshot)  # No limit specified

    lines = result.split("\n")
    assert len(lines) == 50  # Default limit


def test_format_snapshot_empty():
    """Test formatting empty snapshot."""
    snapshot = Snapshot(status="success", url="https://example.com", elements=[])
    result = format_snapshot_for_llm(snapshot)

    assert result == ""
