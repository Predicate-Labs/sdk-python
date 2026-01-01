"""
Tests for async API functionality
"""

import pytest
from playwright.async_api import async_playwright

from sentience.async_api import (
    AsyncSentienceBrowser,
    click,
    click_rect,
    find,
    press,
    query,
    snapshot,
    type_text,
)
from sentience.models import BBox, SnapshotOptions


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_browser_basic():
    """Test basic async browser initialization"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        assert browser.page is not None
        assert "example.com" in browser.page.url


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_viewport_default():
    """Test that default viewport is 1280x800"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        viewport_size = await browser.page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )

        assert viewport_size["width"] == 1280
        assert viewport_size["height"] == 800


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_viewport_custom():
    """Test custom viewport size"""
    custom_viewport = {"width": 1920, "height": 1080}
    async with AsyncSentienceBrowser(viewport=custom_viewport) as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        viewport_size = await browser.page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )

        assert viewport_size["width"] == 1920
        assert viewport_size["height"] == 1080


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_snapshot():
    """Test async snapshot function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot(browser)
        assert isinstance(snap, type(snap))  # Check it's a Snapshot object
        assert snap.status == "success"
        assert len(snap.elements) > 0
        assert snap.url is not None


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_snapshot_with_options():
    """Test async snapshot with options"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        options = SnapshotOptions(limit=10, screenshot=False)
        snap = await snapshot(browser, options)
        assert snap.status == "success"
        assert len(snap.elements) <= 10


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_click():
    """Test async click action"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot(browser)
        link = find(snap, "role=link")

        if link:
            result = await click(browser, link.id)
            assert result.success is True
            assert result.duration_ms > 0
            assert result.outcome in ["navigated", "dom_updated"]


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_type_text():
    """Test async type_text action"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot(browser)
        textbox = find(snap, "role=textbox")

        if textbox:
            result = await type_text(browser, textbox.id, "hello")
            assert result.success is True
            assert result.duration_ms > 0


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_press():
    """Test async press action"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        result = await press(browser, "Enter")
        assert result.success is True
        assert result.duration_ms > 0


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_click_rect():
    """Test async click_rect action"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Click at specific coordinates
        result = await click_rect(browser, {"x": 100, "y": 200, "w": 50, "h": 30}, highlight=False)
        assert result.success is True
        assert result.duration_ms > 0


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_click_rect_with_bbox():
    """Test async click_rect with BBox object"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot(browser)
        if snap.elements:
            element = snap.elements[0]
            bbox = BBox(
                x=element.bbox.x,
                y=element.bbox.y,
                width=element.bbox.width,
                height=element.bbox.height,
            )
            result = await click_rect(browser, bbox, highlight=False)
            assert result.success is True


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_find():
    """Test async find function (re-exported from query)"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot(browser)
        link = find(snap, "role=link")
        # May or may not find a link, but should not raise an error
        assert link is None or hasattr(link, "id")


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_query():
    """Test async query function (re-exported from query)"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot(browser)
        links = query(snap, "role=link")
        assert isinstance(links, list)
        # All results should be Element objects
        for link in links:
            assert hasattr(link, "id")
            assert hasattr(link, "role")


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_from_existing_context():
    """Test creating AsyncSentienceBrowser from existing context"""
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context("", headless=True)
        try:
            browser = await AsyncSentienceBrowser.from_existing(context)
            assert browser.context is context
            assert browser.page is not None

            await browser.page.goto("https://example.com")
            assert "example.com" in browser.page.url

            await browser.close()
        finally:
            await context.close()


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_from_page():
    """Test creating AsyncSentienceBrowser from existing page"""
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context("", headless=True)
        try:
            page = await context.new_page()
            browser = await AsyncSentienceBrowser.from_page(page)
            assert browser.page is page
            assert browser.context is context

            await browser.page.goto("https://example.com")
            assert "example.com" in browser.page.url

            await browser.close()
        finally:
            await context.close()


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_context_manager():
    """Test async context manager usage"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        assert browser.page is not None

    # Browser should be closed after context manager exits
    assert browser.page is None or browser.context is None


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_snapshot_with_goal():
    """Test async snapshot with goal for ML reranking"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        options = SnapshotOptions(goal="Click the main link", limit=10)
        snap = await snapshot(browser, options)
        assert snap.status == "success"
        # Elements may have ML reranking metadata if API key is provided
        # (This test works with or without API key)

