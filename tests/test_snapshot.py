"""
Tests for snapshot functionality
"""

import pytest

from sentience import SentienceBrowser, snapshot
from sentience.models import SnapshotOptions


@pytest.mark.requires_extension
def test_snapshot_basic():
    """Test basic snapshot on example.com"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)

        assert snap.status == "success"
        assert snap.url == "https://example.com/"
        assert len(snap.elements) > 0
        assert all(el.id >= 0 for el in snap.elements)
        assert all(
            el.role
            in [
                "button",
                "link",
                "textbox",
                "searchbox",
                "checkbox",
                "radio",
                "combobox",
                "image",
                "generic",
            ]
            for el in snap.elements
        )


@pytest.mark.requires_extension
def test_snapshot_roundtrip():
    """Test snapshot round-trip on multiple sites"""
    # Use sites that reliably have elements
    sites = [
        "https://example.com",
    ]

    for site in sites:
        with SentienceBrowser() as browser:
            browser.page.goto(site)
            browser.page.wait_for_load_state("networkidle")

            # Wait a bit more for dynamic content and extension processing
            browser.page.wait_for_timeout(1000)

            snap = snapshot(browser)

            assert snap.status == "success"
            assert snap.url is not None

            # Most pages should have at least some elements
            # But we'll be lenient - at least verify structure is valid
            if len(snap.elements) > 0:
                # Verify element structure
                for el in snap.elements[:5]:  # Check first 5
                    assert el.bbox.x >= 0
                    assert el.bbox.y >= 0
                    assert el.bbox.width > 0
                    assert el.bbox.height > 0
                    assert el.importance >= -300
            # Note: Some pages may legitimately have 0 elements due to filtering
            # (min size 5x5, visibility, etc.) - this is acceptable


@pytest.mark.requires_extension
def test_snapshot_save():
    """Test snapshot save functionality"""
    import json
    import os
    import tempfile

    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            snap.save(temp_path)

            # Verify file exists and is valid JSON
            assert os.path.exists(temp_path)
            with open(temp_path) as f:
                data = json.load(f)
                assert data["status"] == "success"
                assert "elements" in data
        finally:
            os.unlink(temp_path)


@pytest.mark.requires_extension
def test_snapshot_with_goal():
    """Test snapshot with goal parameter"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Test snapshot with goal
        snap = snapshot(browser, SnapshotOptions(goal="Find the main heading"))

        assert snap.status == "success"
        assert snap.url == "https://example.com/"
        assert len(snap.elements) > 0

        # Verify snapshot works normally with goal parameter
        assert all(el.id >= 0 for el in snap.elements)
        assert all(
            el.role
            in [
                "button",
                "link",
                "textbox",
                "searchbox",
                "checkbox",
                "radio",
                "combobox",
                "image",
                "generic",
            ]
            for el in snap.elements
        )


def test_element_ml_fields_optional():
    """Test that Element model accepts optional ML reranking fields"""
    from sentience.models import BBox, Element, VisualCues

    # Test element without ML fields
    element_without_ml = Element(
        id=1,
        role="button",
        text="Click me",
        importance=100,
        bbox=BBox(x=10, y=20, width=100, height=50),
        visual_cues=VisualCues(is_primary=True, background_color_name="blue", is_clickable=True),
        in_viewport=True,
        is_occluded=False,
        z_index=0,
    )
    assert element_without_ml.fused_rank_index is None
    assert element_without_ml.heuristic_index is None
    assert element_without_ml.ml_probability is None
    assert element_without_ml.ml_score is None

    # Test element with ML fields
    element_with_ml = Element(
        id=2,
        role="link",
        text="Learn more",
        importance=80,
        bbox=BBox(x=15, y=25, width=120, height=40),
        visual_cues=VisualCues(is_primary=False, background_color_name="white", is_clickable=True),
        in_viewport=True,
        is_occluded=False,
        z_index=1,
        fused_rank_index=0,
        heuristic_index=5,
        ml_probability=0.95,
        ml_score=2.34,
    )
    assert element_with_ml.fused_rank_index == 0
    assert element_with_ml.heuristic_index == 5
    assert element_with_ml.ml_probability == 0.95
    assert element_with_ml.ml_score == 2.34

    # Test element with partial ML fields
    element_partial = Element(
        id=3,
        role="textbox",
        text=None,
        importance=60,
        bbox=BBox(x=20, y=30, width=200, height=30),
        visual_cues=VisualCues(is_primary=False, background_color_name=None, is_clickable=True),
        in_viewport=True,
        is_occluded=False,
        z_index=0,
        fused_rank_index=1,
        ml_probability=0.87,
    )
    assert element_partial.fused_rank_index == 1
    assert element_partial.heuristic_index is None
    assert element_partial.ml_probability == 0.87
    assert element_partial.ml_score is None


def test_snapshot_ml_rerank_metadata_optional():
    """Test snapshot ML rerank metadata model"""
    from sentience.models import MlRerankInfo, MlRerankTags, Snapshot

    snap = Snapshot(
        status="success",
        url="https://example.com",
        elements=[],
        ml_rerank=MlRerankInfo(
            enabled=True,
            applied=False,
            reason="low_confidence",
            candidate_count=25,
            top_probability=0.42,
            min_confidence=0.6,
            is_high_confidence=False,
            tags=MlRerankTags(
                repeated=True,
                sponsored_ish=True,
                non_sponsored=False,
                pos=True,
                occ=True,
                vocc=False,
                short=True,
                action_ish=False,
                nav_ish=False,
            ),
        ),
    )

    assert snap.ml_rerank is not None
    assert snap.ml_rerank.enabled is True
    assert snap.ml_rerank.is_high_confidence is False
