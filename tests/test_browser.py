"""
Tests for SentienceBrowser functionality
"""

import pytest
from playwright.sync_api import sync_playwright

from sentience import SentienceBrowser


@pytest.mark.requires_extension
def test_viewport_default():
    """Test that default viewport is 1280x800"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Get actual viewport size from page
        viewport_size = browser.page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )

        assert viewport_size["width"] == 1280
        assert viewport_size["height"] == 800


@pytest.mark.requires_extension
def test_viewport_custom():
    """Test custom viewport size"""
    custom_viewport = {"width": 1920, "height": 1080}
    with SentienceBrowser(viewport=custom_viewport) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Get actual viewport size from page
        viewport_size = browser.page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )

        assert viewport_size["width"] == 1920
        assert viewport_size["height"] == 1080


@pytest.mark.requires_extension
def test_viewport_mobile():
    """Test mobile viewport size"""
    mobile_viewport = {"width": 375, "height": 667}
    with SentienceBrowser(viewport=mobile_viewport) as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Get actual viewport size from page
        viewport_size = browser.page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )

        assert viewport_size["width"] == 375
        assert viewport_size["height"] == 667


@pytest.mark.requires_extension
def test_from_existing_context():
    """Test creating SentienceBrowser from existing Playwright context"""
    with sync_playwright() as p:
        # Create a browser context with custom settings
        context = p.chromium.launch_persistent_context(
            user_data_dir="",
            headless=False,
            viewport={"width": 1600, "height": 900},
        )

        try:
            # Create SentienceBrowser from existing context
            browser = SentienceBrowser.from_existing(context)

            # Verify it works
            assert browser.context == context
            assert browser.page is not None

            # Test that we can use it
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("networkidle")

            # Verify viewport is preserved
            viewport_size = browser.page.evaluate(
                "() => ({ width: window.innerWidth, height: window.innerHeight })"
            )
            assert viewport_size["width"] == 1600
            assert viewport_size["height"] == 900

        finally:
            context.close()


@pytest.mark.requires_extension
def test_from_page():
    """Test creating SentienceBrowser from existing Playwright page"""
    with sync_playwright() as p:
        browser_instance = p.chromium.launch(headless=False)
        context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # Create SentienceBrowser from existing page
            sentience_browser = SentienceBrowser.from_page(page)

            # Verify it works
            assert sentience_browser.page == page
            assert sentience_browser.context == context

            # Test that we can use it
            page.goto("https://example.com")
            page.wait_for_load_state("networkidle")

            # Verify viewport is preserved
            viewport_size = page.evaluate(
                "() => ({ width: window.innerWidth, height: window.innerHeight })"
            )
            assert viewport_size["width"] == 1440
            assert viewport_size["height"] == 900

        finally:
            context.close()
            browser_instance.close()


@pytest.mark.requires_extension
def test_from_existing_with_api_key():
    """Test from_existing() with API key configuration"""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="",
            headless=False,
        )

        try:
            # Create SentienceBrowser with API key
            browser = SentienceBrowser.from_existing(
                context, api_key="test_key", api_url="https://test.api.com"
            )

            assert browser.api_key == "test_key"
            assert browser.api_url == "https://test.api.com"
            assert browser.context == context

        finally:
            context.close()


@pytest.mark.requires_extension
def test_from_page_with_api_key():
    """Test from_page() with API key configuration"""
    with sync_playwright() as p:
        browser_instance = p.chromium.launch(headless=False)
        context = browser_instance.new_context()
        page = context.new_page()

        try:
            # Create SentienceBrowser with API key
            sentience_browser = SentienceBrowser.from_page(
                page, api_key="test_key", api_url="https://test.api.com"
            )

            assert sentience_browser.api_key == "test_key"
            assert sentience_browser.api_url == "https://test.api.com"
            assert sentience_browser.page == page

        finally:
            context.close()
            browser_instance.close()

