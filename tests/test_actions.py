"""
Tests for actions (click, type, press, click_rect)
"""

import pytest

from sentience import (
    BBox,
    SentienceBrowser,
    click,
    click_rect,
    find,
    press,
    scroll_to,
    snapshot,
    type_text,
)


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


def test_click_rect():
    """Test click_rect with rect dict"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Click at a specific rectangle (top-left area)
        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30})
        assert result.success is True
        assert result.duration_ms > 0
        assert result.outcome in ["navigated", "dom_updated"]


def test_click_rect_with_bbox():
    """Test click_rect with BBox object"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Get an element and click its bbox
        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            result = click_rect(
                browser,
                {
                    "x": link.bbox.x,
                    "y": link.bbox.y,
                    "w": link.bbox.width,
                    "h": link.bbox.height,
                },
            )
            assert result.success is True
            assert result.duration_ms > 0


def test_click_rect_without_highlight():
    """Test click_rect without visual highlight"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30}, highlight=False)
        assert result.success is True
        assert result.duration_ms > 0


def test_click_rect_invalid_rect():
    """Test click_rect with invalid rectangle dimensions"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Invalid: zero width
        result = click_rect(browser, {"x": 100, "y": 100, "w": 0, "h": 30})
        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == "invalid_rect"

        # Invalid: negative height
        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": -10})
        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == "invalid_rect"


def test_click_rect_with_snapshot():
    """Test click_rect with snapshot after action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30}, take_snapshot=True)
        assert result.success is True
        assert result.snapshot_after is not None
        assert result.snapshot_after.status == "success"
        assert len(result.snapshot_after.elements) > 0


def test_click_hybrid_approach():
    """Test that click() uses hybrid approach (mouse.click at center)"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            # Test hybrid approach (mouse.click at center)
            result = click(browser, link.id, use_mouse=True)
            assert result.success is True
            assert result.duration_ms > 0
            # Navigation may happen, which is expected for links
            assert result.outcome in ["navigated", "dom_updated"]


def test_click_js_approach():
    """Test that click() can use JS-based approach (legacy)"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            # Test JS-based click (legacy approach)
            result = click(browser, link.id, use_mouse=False)
            assert result.success is True
            assert result.duration_ms > 0
            # Navigation may happen, which is expected for links
            assert result.outcome in ["navigated", "dom_updated"]


def test_scroll_to():
    """Test scroll_to action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        # Find an element to scroll to (typically the last link or element)
        elements = [el for el in snap.elements if el.role == "link"]

        if elements:
            # Get the last element which might be out of viewport
            element = elements[-1] if len(elements) > 1 else elements[0]
            result = scroll_to(browser, element.id)
            assert result.success is True
            assert result.duration_ms > 0
            assert result.outcome in ["navigated", "dom_updated"]


def test_scroll_to_instant():
    """Test scroll_to with instant behavior"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        elements = [el for el in snap.elements if el.role == "link"]

        if elements:
            element = elements[0]
            result = scroll_to(browser, element.id, behavior="instant", block="start")
            assert result.success is True
            assert result.duration_ms > 0


def test_scroll_to_with_snapshot():
    """Test scroll_to with snapshot after action"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        elements = [el for el in snap.elements if el.role == "link"]

        if elements:
            element = elements[0]
            result = scroll_to(browser, element.id, take_snapshot=True)
            assert result.success is True
            assert result.snapshot_after is not None
            assert result.snapshot_after.status == "success"


def test_scroll_to_invalid_element():
    """Test scroll_to with invalid element ID"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Try to scroll to non-existent element
        result = scroll_to(browser, 99999)
        assert result.success is False
        assert result.error is not None
        assert result.error["code"] == "scroll_failed"


def test_type_text_with_delay():
    """Test type_text with human-like delay"""
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        snap = snapshot(browser)
        textbox = find(snap, "role=textbox")

        if textbox:
            # Test with 10ms delay between keystrokes
            result = type_text(browser, textbox.id, "hello", delay_ms=10)
            assert result.success is True
            # Duration should be longer due to delays
            assert result.duration_ms >= 50  # At least 5 chars * 10ms
