"""
Tests for trace event builder functionality.
"""

import pytest

from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues
from sentience.snapshot_diff import SnapshotDiff
from sentience.trace_event_builder import TraceEventBuilder


def create_element(
    element_id: int,
    role: str = "button",
    text: str | None = "Test",
    x: float = 100.0,
    y: float = 100.0,
    width: float = 50.0,
    height: float = 20.0,
    diff_status: str | None = None,
) -> Element:
    """Helper to create test elements."""
    return Element(
        id=element_id,
        role=role,
        text=text,
        importance=500,
        bbox=BBox(x=x, y=y, width=width, height=height),
        visual_cues=VisualCues(is_primary=False, is_clickable=True),
        diff_status=diff_status,
    )


def create_snapshot(elements: list[Element], url: str = "http://example.com") -> Snapshot:
    """Helper to create test snapshots."""
    return Snapshot(
        status="success",
        url=url,
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
    )


def test_build_step_end_event_basic():
    """Test basic step_end event building without elements."""
    llm_data = {
        "response_text": "click(123)",
        "response_hash": "sha256:abc123",
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }

    exec_data = {
        "success": True,
        "action": "click",
        "outcome": "Clicked element 123",
        "duration_ms": 500,
        "element_id": 123,
    }

    verify_data = {
        "passed": True,
        "signals": {"url_changed": True},
    }

    result = TraceEventBuilder.build_step_end_event(
        step_id="step-1",
        step_index=1,
        goal="Click the button",
        attempt=0,
        pre_url="http://example.com/page1",
        post_url="http://example.com/page2",
        snapshot_digest="sha256:digest123",
        llm_data=llm_data,
        exec_data=exec_data,
        verify_data=verify_data,
    )

    assert result["v"] == 1
    assert result["step_id"] == "step-1"
    assert result["step_index"] == 1
    assert result["goal"] == "Click the button"
    assert result["attempt"] == 0
    assert result["pre"]["url"] == "http://example.com/page1"
    assert result["pre"]["snapshot_digest"] == "sha256:digest123"
    assert "elements" not in result["pre"]  # No elements provided
    assert result["post"]["url"] == "http://example.com/page2"
    assert result["llm"] == llm_data
    assert result["exec"] == exec_data
    assert result["verify"] == verify_data


def test_build_step_end_event_with_elements():
    """Test step_end event building with elements array (for diff overlay)."""
    # Create snapshot with diff_status
    elements = [
        create_element(1, text="Button 1", diff_status="ADDED"),
        create_element(2, text="Button 2", diff_status=None),
        create_element(3, text="Button 3", diff_status="MODIFIED"),
    ]
    snapshot = create_snapshot(elements)

    # Build snapshot event to get formatted elements
    snapshot_event_data = TraceEventBuilder.build_snapshot_event(snapshot)
    pre_elements = snapshot_event_data.get("elements", [])

    llm_data = {
        "response_text": "click(1)",
        "response_hash": "sha256:abc123",
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }

    exec_data = {
        "success": True,
        "action": "click",
        "outcome": "Clicked element 1",
        "duration_ms": 500,
        "element_id": 1,
    }

    verify_data = {
        "passed": True,
        "signals": {"url_changed": True},
    }

    result = TraceEventBuilder.build_step_end_event(
        step_id="step-1",
        step_index=1,
        goal="Click the button",
        attempt=0,
        pre_url="http://example.com/page1",
        post_url="http://example.com/page2",
        snapshot_digest="sha256:digest123",
        llm_data=llm_data,
        exec_data=exec_data,
        verify_data=verify_data,
        pre_elements=pre_elements,
    )

    # Verify elements are included in pre field
    assert "elements" in result["pre"]
    assert len(result["pre"]["elements"]) == 3

    # Verify element data structure
    el1 = result["pre"]["elements"][0]
    assert el1["id"] == 1
    assert el1["role"] == "button"
    assert el1["text"] == "Button 1"
    assert el1["diff_status"] == "ADDED"
    assert "bbox" in el1
    assert "importance" in el1
    assert "importance_score" in el1

    el2 = result["pre"]["elements"][1]
    assert el2["id"] == 2
    assert el2["diff_status"] is None

    el3 = result["pre"]["elements"][2]
    assert el3["id"] == 3
    assert el3["diff_status"] == "MODIFIED"


def test_build_step_end_event_with_diff_status_integration():
    """Test full integration: compute diff_status, build snapshot event, include in step_end."""
    # Previous snapshot
    previous_elements = [
        create_element(1, text="Button 1"),
        create_element(2, text="Old Text"),
    ]
    previous_snapshot = create_snapshot(previous_elements)

    # Current snapshot
    current_elements = [
        create_element(1, text="Button 1"),  # Unchanged
        create_element(2, text="New Text"),  # Modified
        create_element(3, text="New Button"),  # Added
    ]
    current_snapshot = create_snapshot(current_elements)

    # Compute diff_status
    elements_with_diff = SnapshotDiff.compute_diff_status(current_snapshot, previous_snapshot)

    # Create snapshot with diff_status
    snapshot_with_diff = Snapshot(
        status=current_snapshot.status,
        url=current_snapshot.url,
        viewport=current_snapshot.viewport,
        elements=elements_with_diff,
        timestamp=current_snapshot.timestamp,
        screenshot=current_snapshot.screenshot,
        screenshot_format=current_snapshot.screenshot_format,
        error=current_snapshot.error,
    )

    # Build snapshot event to get formatted elements
    snapshot_event_data = TraceEventBuilder.build_snapshot_event(snapshot_with_diff)
    pre_elements = snapshot_event_data.get("elements", [])

    # Build step_end event
    result = TraceEventBuilder.build_step_end_event(
        step_id="step-1",
        step_index=1,
        goal="Click the button",
        attempt=0,
        pre_url="http://example.com",
        post_url="http://example.com",
        snapshot_digest="sha256:digest123",
        llm_data={"response_text": "click(3)", "response_hash": "sha256:xyz"},
        exec_data={"success": True, "action": "click"},
        verify_data={"passed": True, "signals": {}},
        pre_elements=pre_elements,
    )

    # Verify elements are in step_end event with correct diff_status
    assert "elements" in result["pre"]
    # Should have 3 elements (1 unchanged, 1 modified, 1 added)
    # Note: REMOVED elements are also included in diff computation but not in current snapshot
    assert len(result["pre"]["elements"]) == 3

    # Find elements by ID
    elements_by_id = {el["id"]: el for el in result["pre"]["elements"]}

    # Element 1: unchanged (diff_status should be None)
    assert elements_by_id[1]["diff_status"] is None

    # Element 2: modified
    assert elements_by_id[2]["diff_status"] == "MODIFIED"

    # Element 3: added
    assert elements_by_id[3]["diff_status"] == "ADDED"


def test_build_snapshot_event_with_importance_score():
    """Test that build_snapshot_event includes importance_score normalization."""
    elements = [
        create_element(1, text="Low importance", diff_status="ADDED"),
        create_element(2, text="Medium importance", diff_status=None),
        create_element(3, text="High importance", diff_status="MODIFIED"),
    ]
    # Set different importance values
    elements[0].importance = 100
    elements[1].importance = 500
    elements[2].importance = 1000

    snapshot = create_snapshot(elements)
    result = TraceEventBuilder.build_snapshot_event(snapshot)

    # Verify importance_score is normalized to [0, 1]
    assert result["elements"][0]["importance_score"] == 0.0  # Min
    assert result["elements"][1]["importance_score"] == pytest.approx(0.444, abs=0.01)  # Mid
    assert result["elements"][2]["importance_score"] == 1.0  # Max


def test_build_step_end_event_empty_elements():
    """Test step_end event with empty elements array."""
    snapshot = create_snapshot([])  # No elements
    snapshot_event_data = TraceEventBuilder.build_snapshot_event(snapshot)
    pre_elements = snapshot_event_data.get("elements", [])

    result = TraceEventBuilder.build_step_end_event(
        step_id="step-1",
        step_index=1,
        goal="Navigate to page",
        attempt=0,
        pre_url="http://example.com",
        post_url="http://example.com",
        snapshot_digest="sha256:digest123",
        llm_data={"response_text": "navigate", "response_hash": "sha256:xyz"},
        exec_data={"success": True, "action": "navigate"},
        verify_data={"passed": True, "signals": {}},
        pre_elements=pre_elements,
    )

    # Should have elements field but it's empty
    assert "elements" in result["pre"]
    assert len(result["pre"]["elements"]) == 0


def test_build_step_end_event_with_none_verify_data():
    """Test step_end event building when verify_data is None (failed steps).

    This test ensures that failed steps can emit step_end events even when
    verify_data is None, which happens when a step fails before verification.
    """
    llm_data = {
        "response_text": "click(123)",
        "response_hash": "sha256:abc123",
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }

    exec_data = {
        "success": False,
        "action": "error",
        "outcome": "Element not found",
        "duration_ms": 500,
    }

    # verify_data is None for failed steps
    result = TraceEventBuilder.build_step_end_event(
        step_id="step-1",
        step_index=1,
        goal="Click the button",
        attempt=2,
        pre_url="http://example.com/page1",
        post_url="http://example.com/page1",
        snapshot_digest="sha256:digest123",
        llm_data=llm_data,
        exec_data=exec_data,
        verify_data=None,  # None for failed steps
    )

    # Verify basic structure
    assert result["v"] == 1
    assert result["step_id"] == "step-1"
    assert result["step_index"] == 1
    assert result["attempt"] == 2

    # Verify exec shows failure
    assert result["exec"]["success"] is False
    assert result["exec"]["action"] == "error"

    # Verify should be empty dict when verify_data is None
    assert result["verify"] == {}


def test_build_snapshot_event_with_step_index():
    """Test that build_snapshot_event includes step_index when provided.

    This is required for AgentRuntime which uses UUID step_ids that can't be
    parsed by Studio's trace-parser to extract step_index.
    """
    elements = [create_element(1, text="Test element")]
    snapshot = create_snapshot(elements)

    # Without step_index
    result_without = TraceEventBuilder.build_snapshot_event(snapshot)
    assert "step_index" not in result_without

    # With step_index=0
    result_with_zero = TraceEventBuilder.build_snapshot_event(snapshot, step_index=0)
    assert result_with_zero["step_index"] == 0

    # With step_index=5
    result_with_five = TraceEventBuilder.build_snapshot_event(snapshot, step_index=5)
    assert result_with_five["step_index"] == 5
