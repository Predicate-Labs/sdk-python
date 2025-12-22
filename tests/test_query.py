"""
Tests for query engine
"""

from sentience import SentienceBrowser, snapshot, query, find
from sentience.query import parse_selector, match_element
from sentience.models import Element, BBox, VisualCues


def test_parse_selector():
    """Test selector parsing"""
    # Simple role
    q = parse_selector("role=button")
    assert q["role"] == "button"
    
    # Text contains
    q = parse_selector("text~'Sign in'")
    assert q["text_contains"] == "Sign in"
    
    # Clickable
    q = parse_selector("clickable=true")
    assert q["clickable"] is True
    
    # Combined
    q = parse_selector("role=button text~'Submit'")
    assert q["role"] == "button"
    assert q["text_contains"] == "Submit"
    
    # Negation
    q = parse_selector("role!=link")
    assert q["role_exclude"] == "link"
    
    # New operators: prefix and suffix
    q = parse_selector("text^='Sign'")
    assert q["text_prefix"] == "Sign"
    
    q = parse_selector("text$='in'")
    assert q["text_suffix"] == "in"
    
    # Numeric comparisons: importance
    q = parse_selector("importance>500")
    assert "importance_min" in q
    assert q["importance_min"] > 500
    
    q = parse_selector("importance>=500")
    assert q["importance_min"] == 500
    
    q = parse_selector("importance<1000")
    assert "importance_max" in q
    assert q["importance_max"] < 1000
    
    q = parse_selector("importance<=1000")
    assert q["importance_max"] == 1000
    
    # Visible field
    q = parse_selector("visible=true")
    assert q["visible"] is True
    
    q = parse_selector("visible=false")
    assert q["visible"] is False
    
    # Tag field (placeholder for future)
    q = parse_selector("tag=button")
    assert q["tag"] == "button"


def test_match_element():
    """Test element matching"""
    element = Element(
        id=1,
        role="button",
        text="Sign In",
        importance=100,
        bbox=BBox(x=0, y=0, width=100, height=40),
        visual_cues=VisualCues(is_primary=True, is_clickable=True),
        in_viewport=True,
        is_occluded=False,
        z_index=10,
    )
    
    # Role match
    assert match_element(element, {"role": "button"}) is True
    assert match_element(element, {"role": "link"}) is False
    
    # Text contains
    assert match_element(element, {"text_contains": "Sign"}) is True
    assert match_element(element, {"text_contains": "Logout"}) is False
    
    # Text prefix
    assert match_element(element, {"text_prefix": "Sign"}) is True
    assert match_element(element, {"text_prefix": "Login"}) is False
    
    # Text suffix
    assert match_element(element, {"text_suffix": "In"}) is True
    assert match_element(element, {"text_suffix": "Out"}) is False
    
    # Clickable
    assert match_element(element, {"clickable": True}) is True
    assert match_element(element, {"clickable": False}) is False
    
    # Visible (using in_viewport and !is_occluded)
    assert match_element(element, {"visible": True}) is True
    element_occluded = Element(
        id=2,
        role="button",
        text="Hidden",
        importance=50,
        bbox=BBox(x=0, y=0, width=100, height=40),
        visual_cues=VisualCues(is_primary=False, is_clickable=True),
        in_viewport=True,
        is_occluded=True,
        z_index=5,
    )
    assert match_element(element_occluded, {"visible": True}) is False
    assert match_element(element_occluded, {"visible": False}) is True
    
    # Importance filtering
    assert match_element(element, {"importance_min": 50}) is True
    assert match_element(element, {"importance_min": 150}) is False
    assert match_element(element, {"importance_max": 150}) is True
    assert match_element(element, {"importance_max": 50}) is False
    
    # BBox filtering
    assert match_element(element, {"bbox.x_min": -10}) is True
    assert match_element(element, {"bbox.x_min": 10}) is False
    assert match_element(element, {"bbox.width_min": 50}) is True
    assert match_element(element, {"bbox.width_min": 150}) is False
    
    # Z-index filtering
    assert match_element(element, {"z_index_min": 5}) is True
    assert match_element(element, {"z_index_min": 15}) is False
    assert match_element(element, {"z_index_max": 15}) is True
    assert match_element(element, {"z_index_max": 5}) is False
    
    # In viewport filtering
    assert match_element(element, {"in_viewport": True}) is True
    element_off_screen = Element(
        id=3,
        role="button",
        text="Off Screen",
        importance=50,
        bbox=BBox(x=0, y=0, width=100, height=40),
        visual_cues=VisualCues(is_primary=False, is_clickable=True),
        in_viewport=False,
        is_occluded=False,
        z_index=5,
    )
    assert match_element(element_off_screen, {"in_viewport": False}) is True
    assert match_element(element_off_screen, {"in_viewport": True}) is False
    
    # Occlusion filtering
    assert match_element(element, {"is_occluded": False}) is True
    assert match_element(element_occluded, {"is_occluded": True}) is True


def test_query_integration():
    """Test query on real page"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        
        # Query for links
        links = query(snap, "role=link")
        assert len(links) > 0
        assert all(el.role == "link" for el in links)
        
        # Query for clickable
        clickables = query(snap, "clickable=true")
        assert len(clickables) > 0
        assert all(el.visual_cues.is_clickable for el in clickables)


def test_find_integration():
    """Test find on real page"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        
        # Find first link
        link = find(snap, "role=link")
        if link:
            assert link.role == "link"
            assert link.id >= 0


def test_query_advanced_operators():
    """Test advanced query operators"""
    # Create test elements
    elements = [
        Element(
            id=1,
            role="button",
            text="Sign In",
            importance=1000,
            bbox=BBox(x=10, y=20, width=100, height=40),
            visual_cues=VisualCues(is_primary=True, is_clickable=True),
            in_viewport=True,
            is_occluded=False,
            z_index=10,
        ),
        Element(
            id=2,
            role="button",
            text="Sign Out",
            importance=500,
            bbox=BBox(x=120, y=20, width=100, height=40),
            visual_cues=VisualCues(is_primary=False, is_clickable=True),
            in_viewport=True,
            is_occluded=False,
            z_index=5,
        ),
        Element(
            id=3,
            role="link",
            text="More information",
            importance=200,
            bbox=BBox(x=10, y=70, width=150, height=20),
            visual_cues=VisualCues(is_primary=False, is_clickable=True),
            in_viewport=True,
            is_occluded=False,
            z_index=1,
        ),
    ]
    
    from sentience.models import Snapshot
    snap = Snapshot(
        status="success",
        url="https://example.com",
        elements=elements,
    )
    
    # Test importance filtering
    high_importance = query(snap, "importance>500")
    assert len(high_importance) == 1
    assert high_importance[0].id == 1
    
    low_importance = query(snap, "importance<300")
    assert len(low_importance) == 1
    assert low_importance[0].id == 3
    
    # Test prefix matching
    sign_prefix = query(snap, "text^='Sign'")
    assert len(sign_prefix) == 2
    assert all("Sign" in el.text for el in sign_prefix)
    
    # Test suffix matching
    in_suffix = query(snap, "text$='In'")
    assert len(in_suffix) == 1
    assert in_suffix[0].text == "Sign In"
    
    # Test BBox filtering
    right_side = query(snap, "bbox.x>100")
    assert len(right_side) == 1
    assert right_side[0].id == 2
    
    # Test combined queries
    combined = query(snap, "role=button importance>500")
    assert len(combined) == 1
    assert combined[0].id == 1
    
    # Test visible filtering
    visible = query(snap, "visible=true")
    assert len(visible) == 3  # All are visible
    
    # Test z-index filtering
    high_z = query(snap, "z_index>5")
    assert len(high_z) == 1
    assert high_z[0].id == 1

