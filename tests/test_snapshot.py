"""
Tests for snapshot functionality
"""

import pytest
from sentience import SentienceBrowser, snapshot
from sentience.models import Snapshot


def test_snapshot_basic():
    """Test basic snapshot on example.com"""
    with SentienceBrowser(headless=False) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        
        assert snap.status == "success"
        assert snap.url == "https://example.com/"
        assert len(snap.elements) > 0
        assert all(el.id >= 0 for el in snap.elements)
        assert all(el.role in ["button", "link", "textbox", "searchbox", "checkbox", "radio", "combobox", "image", "generic"] 
                   for el in snap.elements)


def test_snapshot_roundtrip():
    """Test snapshot round-trip on multiple sites"""
    sites = [
        "https://example.com",
        "https://www.wikipedia.org",
    ]
    
    for site in sites:
        with SentienceBrowser(headless=False) as browser:
            browser.page.goto(site)
            browser.page.wait_for_load_state("networkidle")
            
            snap = snapshot(browser)
            
            assert snap.status == "success"
            assert len(snap.elements) > 0
            
            # Verify element structure
            for el in snap.elements[:5]:  # Check first 5
                assert el.bbox.x >= 0
                assert el.bbox.y >= 0
                assert el.bbox.width > 0
                assert el.bbox.height > 0
                assert el.importance >= -300


def test_snapshot_save():
    """Test snapshot save functionality"""
    import tempfile
    import os
    import json
    
    with SentienceBrowser(headless=False) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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

