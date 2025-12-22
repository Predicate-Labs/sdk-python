"""
Tests for wait functionality
"""

import pytest
import os
from sentience import SentienceBrowser, wait_for, expect


def test_wait_for():
    """Test wait_for element"""
    # Auto-detect headless mode (True in CI, False locally)
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        result = wait_for(browser, "role=link", timeout=5.0)
        assert result.found is True
        assert result.element is not None
        assert result.timeout is False
        assert result.duration_ms > 0


def test_wait_for_timeout():
    """Test wait_for timeout"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        # Wait for non-existent element
        result = wait_for(browser, "role=button text~'NonExistentButton'", timeout=1.0)
        assert result.found is False
        assert result.timeout is True


def test_expect_to_exist():
    """Test expect().to_exist()"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        element = expect(browser, "role=link").to_exist(timeout=5.0)
        assert element is not None
        assert element.role == "link"


def test_expect_to_be_visible():
    """Test expect().to_be_visible()"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        element = expect(browser, "role=link").to_be_visible(timeout=5.0)
        assert element is not None
        assert element.in_viewport is True

