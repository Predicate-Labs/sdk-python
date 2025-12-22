"""
Tests for screenshot functionality
"""

import base64
from sentience import SentienceBrowser, screenshot


def test_screenshot_png():
    """Test capturing PNG screenshot"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        data_url = screenshot(browser, format="png")
        
        assert data_url.startswith("data:image/png;base64,")
        
        # Decode and verify it's valid base64
        base64_data = data_url.split(",")[1]
        image_data = base64.b64decode(base64_data)
        assert len(image_data) > 0


def test_screenshot_jpeg():
    """Test capturing JPEG screenshot"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        data_url = screenshot(browser, format="jpeg", quality=80)
        
        assert data_url.startswith("data:image/jpeg;base64,")
        
        # Decode and verify it's valid base64
        base64_data = data_url.split(",")[1]
        image_data = base64.b64decode(base64_data)
        assert len(image_data) > 0


def test_screenshot_default():
    """Test default screenshot (PNG)"""
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        data_url = screenshot(browser)
        
        assert data_url.startswith("data:image/png;base64,")


def test_screenshot_quality_validation():
    """Test JPEG quality validation"""
    import pytest
    
    with SentienceBrowser(headless=True) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        # Valid quality
        screenshot(browser, format="jpeg", quality=50)  # Should not raise
        
        # Invalid quality - too low
        with pytest.raises(ValueError, match="Quality must be between 1 and 100"):
            screenshot(browser, format="jpeg", quality=0)
        
        # Invalid quality - too high
        with pytest.raises(ValueError, match="Quality must be between 1 and 100"):
            screenshot(browser, format="jpeg", quality=101)

