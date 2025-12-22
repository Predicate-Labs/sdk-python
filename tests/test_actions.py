"""
Tests for actions (click, type, press)
"""

import pytest
from sentience import SentienceBrowser, snapshot, find, click, type_text, press


def test_click():
    """Test click action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        link = find(snap, "role=link")
        
        if link:
            result = click(browser, link.id)
            assert result.success is True
            assert result.duration_ms > 0
            assert result.outcome in ["navigated", "dom_updated"]


def test_type_text():
    """Test type action"""
    with SentienceBrowser() as browser:
        # Use a page with a text input
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        # Find textbox if available
        snap = snapshot(browser)
        textbox = find(snap, "role=textbox")
        
        if textbox:
            result = type_text(browser, textbox.id, "hello")
            assert result.success is True
            assert result.duration_ms > 0


def test_press():
    """Test press action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        result = press(browser, "Enter")
        assert result.success is True
        assert result.duration_ms > 0

