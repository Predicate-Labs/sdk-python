"""
Tests for query engine
"""

import pytest
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


def test_match_element():
    """Test element matching"""
    element = Element(
        id=1,
        role="button",
        text="Sign In",
        importance=100,
        bbox=BBox(x=0, y=0, width=100, height=40),
        visual_cues=VisualCues(is_primary=True, is_clickable=True),
    )
    
    # Role match
    assert match_element(element, {"role": "button"}) is True
    assert match_element(element, {"role": "link"}) is False
    
    # Text contains
    assert match_element(element, {"text_contains": "Sign"}) is True
    assert match_element(element, {"text_contains": "Logout"}) is False
    
    # Clickable
    assert match_element(element, {"clickable": True}) is True
    assert match_element(element, {"clickable": False}) is False


def test_query_integration():
    """Test query on real page"""
    with SentienceBrowser(headless=False) as browser:
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
    with SentienceBrowser(headless=False) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        
        # Find first link
        link = find(snap, "role=link")
        if link:
            assert link.role == "link"
            assert link.id >= 0

