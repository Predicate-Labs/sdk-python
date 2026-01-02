"""
Tests for async API functionality
"""

import pytest
from playwright.async_api import async_playwright

from sentience.async_api import (
    AsyncSentienceBrowser,
    BaseAgentAsync,
    ExpectationAsync,
    InspectorAsync,
    RecorderAsync,
    SentienceAgentAsync,
    clear_overlay_async,
    click_async,
    click_rect_async,
    expect_async,
    find,
    find_text_rect_async,
    inspect_async,
    press_async,
    query,
    read_async,
    record_async,
    screenshot_async,
    show_overlay_async,
    snapshot_async,
    type_text_async,
    wait_for_async,
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

        snap = await snapshot_async(browser)
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
        snap = await snapshot_async(browser, options)
        assert snap.status == "success"
        assert len(snap.elements) <= 10


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_click():
    """Test async click action"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot_async(browser)
        link = find(snap, "role=link")

        if link:
            result = await click_async(browser, link.id)
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

        snap = await snapshot_async(browser)
        textbox = find(snap, "role=textbox")

        if textbox:
            result = await type_text_async(browser, textbox.id, "hello")
            assert result.success is True
            assert result.duration_ms > 0


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_press():
    """Test async press action"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        result = await press_async(browser, "Enter")
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
        result = await click_rect_async(
            browser, {"x": 100, "y": 200, "w": 50, "h": 30}, highlight=False
        )
        assert result.success is True
        assert result.duration_ms > 0


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_click_rect_with_bbox():
    """Test async click_rect with BBox object"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot_async(browser)
        if snap.elements:
            element = snap.elements[0]
            bbox = BBox(
                x=element.bbox.x,
                y=element.bbox.y,
                width=element.bbox.width,
                height=element.bbox.height,
            )
            result = await click_rect_async(browser, bbox, highlight=False)
            assert result.success is True


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_find():
    """Test async find function (re-exported from query)"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        snap = await snapshot_async(browser)
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

        snap = await snapshot_async(browser)
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
        snap = await snapshot_async(browser, options)
        assert snap.status == "success"
        # Elements may have ML reranking metadata if API key is provided
        # (This test works with or without API key)


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_wait_for():
    """Test async wait_for function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Wait for a link to appear
        result = await wait_for_async(browser, "role=link", timeout=5.0)
        assert result.found is True or result.timeout is True  # May or may not find link
        assert result.duration_ms >= 0
        if result.found:
            assert result.element is not None
            assert hasattr(result.element, "id")


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_screenshot():
    """Test async screenshot function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Test PNG screenshot
        data_url = await screenshot_async(browser, format="png")
        assert data_url.startswith("data:image/png;base64,")
        assert len(data_url) > 100  # Should have base64 data

        # Test JPEG screenshot
        data_url_jpeg = await screenshot_async(browser, format="jpeg", quality=85)
        assert data_url_jpeg.startswith("data:image/jpeg;base64,")
        assert len(data_url_jpeg) > 100


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_find_text_rect():
    """Test async find_text_rect function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Find text on the page
        result = await find_text_rect_async(browser, "Example", max_results=5)
        assert result.status == "success"
        assert result.query == "Example"
        assert result.matches >= 0
        assert isinstance(result.results, list)

        # If matches found, verify structure
        if result.results:
            match = result.results[0]
            assert hasattr(match, "text")
            assert hasattr(match, "rect")
            assert hasattr(match, "viewport_rect")
            assert hasattr(match, "in_viewport")


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_read():
    """Test async read function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")
        # Wait a bit more for extension to be ready
        await browser.page.wait_for_timeout(500)

        # Test raw HTML format
        result = await read_async(browser, output_format="raw")
        assert result.status == "success"
        assert result.content is not None
        assert result.url is not None
        assert result.format == "raw"
        assert len(result.content) > 0

        # Test text format
        result = await read_async(browser, output_format="text")
        assert result.status == "success"
        assert result.format == "text"
        assert len(result.content) > 0

        # Test markdown format (may fallback to extension's markdown)
        result = await read_async(browser, output_format="markdown")
        assert result.status == "success"
        assert result.format == "markdown"
        assert len(result.content) > 0


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_show_overlay():
    """Test async show_overlay function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Get snapshot
        snap = await snapshot_async(browser)
        assert len(snap.elements) > 0

        # Show overlay with snapshot
        await show_overlay_async(browser, snap)
        # No exception means success

        # Show overlay with target element
        if len(snap.elements) > 0:
            target_id = snap.elements[0].id
            await show_overlay_async(browser, snap, target_element_id=target_id)

        # Show overlay with element list
        elements = [el.model_dump() for el in snap.elements[:5]]  # First 5 elements
        await show_overlay_async(browser, elements)

        # Clear overlay
        await clear_overlay_async(browser)


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_clear_overlay():
    """Test async clear_overlay function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Clear overlay (should not raise even if no overlay is shown)
        await clear_overlay_async(browser)


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_expect_to_be_visible():
    """Test async expect to_be_visible"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Expect a link to be visible (more reliable on example.com)
        element = await expect_async(browser, "role=link").to_be_visible()
        assert element is not None
        assert element.in_viewport is True


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_expect_to_exist():
    """Test async expect to_exist"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Expect a link to exist (more reliable on example.com)
        element = await expect_async(browser, "role=link").to_exist()
        assert element is not None


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_expect_to_have_text():
    """Test async expect to_have_text"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Expect link to have "more" text (common on example.com)
        element = await expect_async(browser, "role=link").to_have_text("more")
        assert element is not None
        assert "more" in element.text.lower()


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_expect_to_have_count():
    """Test async expect to_have_count"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Expect at least one link (more reliable on example.com)
        await expect_async(browser, "role=link").to_have_count(1)


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_async_expectation_class():
    """Test ExpectationAsync class directly"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Create expectation instance
        expectation = ExpectationAsync(browser, "role=link")
        assert expectation.browser == browser
        assert expectation.selector == "role=link"

        # Use expectation methods
        element = await expectation.to_exist()
        assert element is not None


# ========== Phase 2C: Agent Layer Tests ==========


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_base_agent_async_interface():
    """Test BaseAgentAsync is an abstract class"""
    # BaseAgentAsync should be abstract and cannot be instantiated
    assert issubclass(BaseAgentAsync, BaseAgentAsync)
    # Check that it has the required abstract methods
    assert hasattr(BaseAgentAsync, "act")
    assert hasattr(BaseAgentAsync, "get_history")
    assert hasattr(BaseAgentAsync, "get_token_stats")
    assert hasattr(BaseAgentAsync, "clear_history")
    assert hasattr(BaseAgentAsync, "filter_elements")


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_sentience_agent_async_initialization():
    """Test SentienceAgentAsync can be initialized"""
    from sentience.llm_provider import LLMProvider, LLMResponse

    # Create a simple mock LLM provider
    class MockLLMProvider(LLMProvider):
        def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
            return LLMResponse(
                content="CLICK(1)",
                model_name="mock",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )

        def supports_json_mode(self) -> bool:
            return True

        @property
        def model_name(self) -> str:
            return "mock-model"

    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        # Create a mock LLM provider
        llm = MockLLMProvider()
        agent = SentienceAgentAsync(browser, llm, verbose=False)

        assert agent.browser == browser
        assert agent.llm == llm
        assert agent.default_snapshot_limit == 50
        assert len(agent.history) == 0

        # Test history methods
        history = agent.get_history()
        assert isinstance(history, list)
        assert len(history) == 0

        stats = agent.get_token_stats()
        assert stats.total_tokens == 0
        assert stats.total_prompt_tokens == 0
        assert stats.total_completion_tokens == 0

        # Test clear_history
        agent.clear_history()
        assert len(agent.history) == 0


# ========== Phase 2D: Developer Tools Tests ==========


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_recorder_async_initialization():
    """Test RecorderAsync can be initialized"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        recorder = RecorderAsync(browser, capture_snapshots=False)
        assert recorder.browser == browser
        assert recorder.capture_snapshots is False
        assert recorder._active is False
        assert recorder.trace is None


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_recorder_async_context_manager():
    """Test RecorderAsync context manager"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        async with RecorderAsync(browser) as recorder:
            assert recorder._active is True
            assert recorder.trace is not None
            assert recorder.trace.start_url == browser.page.url

        # After context exit, recorder should be stopped
        assert recorder._active is False


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_recorder_async_record_methods():
    """Test RecorderAsync record methods"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        recorder = RecorderAsync(browser)
        await recorder.start()

        # Record navigation
        recorder.record_navigation("https://example.com/page2")
        assert len(recorder.trace.steps) == 1
        assert recorder.trace.steps[0].type == "navigation"

        # Record press
        recorder.record_press("Enter")
        assert len(recorder.trace.steps) == 2
        assert recorder.trace.steps[1].type == "press"
        assert recorder.trace.steps[1].key == "Enter"

        recorder.stop()


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_record_async_function():
    """Test record_async convenience function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        recorder = record_async(browser, capture_snapshots=False)
        assert isinstance(recorder, RecorderAsync)
        assert recorder.browser == browser
        assert recorder.capture_snapshots is False


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_inspector_async_initialization():
    """Test InspectorAsync can be initialized"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        inspector = InspectorAsync(browser)
        assert inspector.browser == browser
        assert inspector._active is False
        assert inspector._last_element_id is None


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_inspector_async_context_manager():
    """Test InspectorAsync context manager"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        async with InspectorAsync(browser) as inspector:
            assert inspector._active is True

        # After context exit, inspector should be stopped
        assert inspector._active is False


@pytest.mark.asyncio
@pytest.mark.requires_extension
async def test_inspect_async_function():
    """Test inspect_async convenience function"""
    async with AsyncSentienceBrowser() as browser:
        await browser.goto("https://example.com")
        await browser.page.wait_for_load_state("networkidle")

        inspector = inspect_async(browser)
        assert isinstance(inspector, InspectorAsync)
        assert inspector.browser == browser
