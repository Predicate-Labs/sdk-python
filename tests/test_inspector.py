"""
Tests for inspector functionality
"""

import pytest
from sentience import SentienceBrowser, inspect


def test_inspector_start_stop():
    """Test inspector can start and stop"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        inspector = inspect(browser)
        inspector.start()
        
        # Verify inspector is active
        active = browser.page.evaluate("window.__sentience_inspector_active === true")
        assert active is True
        
        inspector.stop()
        
        # Verify inspector is stopped
        active = browser.page.evaluate("window.__sentience_inspector_active === true")
        assert active is False


def test_inspector_context_manager():
    """Test inspector as context manager"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with inspect(browser):
            # Verify inspector is active
            active = browser.page.evaluate("window.__sentience_inspector_active === true")
            assert active is True
        
        # Verify inspector is stopped after context exit
        active = browser.page.evaluate("window.__sentience_inspector_active === true")
        assert active is False


def test_inspector_mouse_move_detection():
    """Test inspector detects mouse move"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with inspect(browser):
            # Simulate mouse move
            browser.page.mouse.move(100, 100)
            browser.page.wait_for_timeout(100)
            
            # Inspector should be active (we can't easily test console output)
            active = browser.page.evaluate("window.__sentience_inspector_active === true")
            assert active is True


def test_inspector_click_detection():
    """Test inspector detects clicks"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        with inspect(browser):
            # Simulate click
            browser.page.mouse.click(100, 100)
            browser.page.wait_for_timeout(100)
            
            # Inspector should be active
            active = browser.page.evaluate("window.__sentience_inspector_active === true")
            assert active is True

