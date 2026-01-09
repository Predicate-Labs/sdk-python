"""
Tests for the backends module.

These tests verify the CDP backend implementation works correctly
without requiring a real browser (using mocked CDP transport).
"""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sentience.backends import (
    BrowserBackendV0,
    BrowserUseAdapter,
    BrowserUseCDPTransport,
    CachedSnapshot,
    CDPBackendV0,
    CDPTransport,
    LayoutMetrics,
    PlaywrightBackend,
    ViewportInfo,
    click,
    scroll,
    type_text,
    wait_for_stable,
)
from sentience.models import ActionResult, BBox


class MockCDPTransport:
    """Mock CDP transport for testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.responses: dict[str, Any] = {}

    def set_response(self, method: str, response: Any) -> None:
        """Set a response for a specific method."""
        self.responses[method] = response

    async def send(self, method: str, params: dict | None = None) -> dict:
        """Record the call and return mock response."""
        self.calls.append((method, params))
        if method in self.responses:
            response = self.responses[method]
            if callable(response):
                return response(params)
            return response
        return {}


class TestViewportInfo:
    """Tests for ViewportInfo model."""

    def test_create_viewport_info(self) -> None:
        """Test creating ViewportInfo with all fields."""
        info = ViewportInfo(
            width=1920,
            height=1080,
            scroll_x=100.0,
            scroll_y=200.0,
            content_width=3000.0,
            content_height=5000.0,
        )
        assert info.width == 1920
        assert info.height == 1080
        assert info.scroll_x == 100.0
        assert info.scroll_y == 200.0
        assert info.content_width == 3000.0
        assert info.content_height == 5000.0

    def test_viewport_info_defaults(self) -> None:
        """Test ViewportInfo default values."""
        info = ViewportInfo(width=800, height=600)
        assert info.scroll_x == 0.0
        assert info.scroll_y == 0.0
        assert info.content_width is None
        assert info.content_height is None


class TestLayoutMetrics:
    """Tests for LayoutMetrics model."""

    def test_create_layout_metrics(self) -> None:
        """Test creating LayoutMetrics with all fields."""
        metrics = LayoutMetrics(
            viewport_x=0.0,
            viewport_y=100.0,
            viewport_width=1920.0,
            viewport_height=1080.0,
            content_width=1920.0,
            content_height=5000.0,
            device_scale_factor=2.0,
        )
        assert metrics.viewport_x == 0.0
        assert metrics.viewport_y == 100.0
        assert metrics.viewport_width == 1920.0
        assert metrics.viewport_height == 1080.0
        assert metrics.content_width == 1920.0
        assert metrics.content_height == 5000.0
        assert metrics.device_scale_factor == 2.0

    def test_layout_metrics_defaults(self) -> None:
        """Test LayoutMetrics default values."""
        metrics = LayoutMetrics()
        assert metrics.viewport_x == 0.0
        assert metrics.viewport_y == 0.0
        assert metrics.viewport_width == 0.0
        assert metrics.viewport_height == 0.0
        assert metrics.content_width == 0.0
        assert metrics.content_height == 0.0
        assert metrics.device_scale_factor == 1.0


class TestCDPBackendV0:
    """Tests for CDPBackendV0 implementation."""

    @pytest.fixture
    def transport(self) -> MockCDPTransport:
        """Create mock transport."""
        return MockCDPTransport()

    @pytest.fixture
    def backend(self, transport: MockCDPTransport) -> CDPBackendV0:
        """Create backend with mock transport."""
        return CDPBackendV0(transport)

    @pytest.mark.asyncio
    async def test_refresh_page_info(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test refresh_page_info returns ViewportInfo."""
        transport.set_response(
            "Runtime.evaluate",
            {
                "result": {
                    "type": "object",
                    "value": {
                        "width": 1920,
                        "height": 1080,
                        "scroll_x": 0,
                        "scroll_y": 100,
                        "content_width": 1920,
                        "content_height": 5000,
                    },
                }
            },
        )

        info = await backend.refresh_page_info()

        assert isinstance(info, ViewportInfo)
        assert info.width == 1920
        assert info.height == 1080
        assert info.scroll_y == 100

    @pytest.mark.asyncio
    async def test_eval(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test eval executes JavaScript and returns value."""
        transport.set_response(
            "Runtime.evaluate",
            {"result": {"type": "number", "value": 42}},
        )

        result = await backend.eval("1 + 1")

        assert result == 42
        assert len(transport.calls) == 1
        assert transport.calls[0][0] == "Runtime.evaluate"
        assert transport.calls[0][1]["expression"] == "1 + 1"

    @pytest.mark.asyncio
    async def test_eval_exception(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test eval raises on JavaScript exception."""
        transport.set_response(
            "Runtime.evaluate",
            {
                "exceptionDetails": {
                    "text": "ReferenceError: foo is not defined",
                }
            },
        )

        with pytest.raises(RuntimeError, match="JavaScript evaluation failed"):
            await backend.eval("foo")

    @pytest.mark.asyncio
    async def test_get_layout_metrics(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test get_layout_metrics returns LayoutMetrics."""
        transport.set_response(
            "Page.getLayoutMetrics",
            {
                "layoutViewport": {"clientWidth": 1920, "clientHeight": 1080},
                "contentSize": {"width": 1920, "height": 5000},
                "visualViewport": {
                    "pageX": 0,
                    "pageY": 100,
                    "clientWidth": 1920,
                    "clientHeight": 1080,
                    "scale": 1.0,
                },
            },
        )

        metrics = await backend.get_layout_metrics()

        assert isinstance(metrics, LayoutMetrics)
        assert metrics.viewport_width == 1920
        assert metrics.viewport_height == 1080
        assert metrics.content_height == 5000

    @pytest.mark.asyncio
    async def test_screenshot_png(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test screenshot_png returns PNG bytes."""
        import base64

        # Create a minimal PNG (1x1 transparent pixel)
        png_data = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        transport.set_response(
            "Page.captureScreenshot",
            {"data": png_data},
        )

        result = await backend.screenshot_png()

        assert isinstance(result, bytes)
        assert result.startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_mouse_move(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test mouse_move dispatches mouseMoved event."""
        await backend.mouse_move(100, 200)

        assert len(transport.calls) == 1
        method, params = transport.calls[0]
        assert method == "Input.dispatchMouseEvent"
        assert params["type"] == "mouseMoved"
        assert params["x"] == 100
        assert params["y"] == 200

    @pytest.mark.asyncio
    async def test_mouse_click(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test mouse_click dispatches press and release events."""
        await backend.mouse_click(100, 200)

        assert len(transport.calls) == 2

        # Check mousePressed
        method, params = transport.calls[0]
        assert method == "Input.dispatchMouseEvent"
        assert params["type"] == "mousePressed"
        assert params["x"] == 100
        assert params["y"] == 200
        assert params["button"] == "left"

        # Check mouseReleased
        method, params = transport.calls[1]
        assert method == "Input.dispatchMouseEvent"
        assert params["type"] == "mouseReleased"

    @pytest.mark.asyncio
    async def test_mouse_click_right_button(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test mouse_click with right button."""
        await backend.mouse_click(100, 200, button="right")

        method, params = transport.calls[0]
        assert params["button"] == "right"

    @pytest.mark.asyncio
    async def test_wheel(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test wheel dispatches mouseWheel event."""
        # First set up viewport info for default coordinates
        transport.set_response(
            "Runtime.evaluate",
            {
                "result": {
                    "type": "object",
                    "value": {"width": 1920, "height": 1080},
                }
            },
        )

        await backend.wheel(delta_y=100, x=500, y=300)

        # Find the wheel event (skip the eval call if it happened)
        wheel_calls = [c for c in transport.calls if c[0] == "Input.dispatchMouseEvent"]
        assert len(wheel_calls) == 1

        method, params = wheel_calls[0]
        assert params["type"] == "mouseWheel"
        assert params["deltaY"] == 100
        assert params["x"] == 500
        assert params["y"] == 300

    @pytest.mark.asyncio
    async def test_type_text(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test type_text dispatches key events for each character."""
        await backend.type_text("Hi")

        # Each character generates keyDown, char, keyUp = 3 events
        # "Hi" = 2 chars = 6 events
        key_events = [c for c in transport.calls if c[0] == "Input.dispatchKeyEvent"]
        assert len(key_events) == 6

        # Check first character 'H'
        assert key_events[0][1]["type"] == "keyDown"
        assert key_events[0][1]["text"] == "H"
        assert key_events[1][1]["type"] == "char"
        assert key_events[2][1]["type"] == "keyUp"

    @pytest.mark.asyncio
    async def test_wait_ready_state_immediate(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test wait_ready_state returns immediately if state is met."""
        transport.set_response(
            "Runtime.evaluate",
            {"result": {"type": "string", "value": "complete"}},
        )

        # Should not raise
        await backend.wait_ready_state(state="complete", timeout_ms=1000)

    @pytest.mark.asyncio
    async def test_wait_ready_state_timeout(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test wait_ready_state raises on timeout."""
        transport.set_response(
            "Runtime.evaluate",
            {"result": {"type": "string", "value": "loading"}},
        )

        with pytest.raises(TimeoutError, match="Timed out"):
            await backend.wait_ready_state(state="complete", timeout_ms=200)


class TestCDPBackendProtocol:
    """Test that CDPBackendV0 implements BrowserBackendV0 protocol."""

    def test_implements_protocol(self) -> None:
        """Verify CDPBackendV0 is recognized as BrowserBackendV0."""
        transport = MockCDPTransport()
        backend = CDPBackendV0(transport)
        assert isinstance(backend, BrowserBackendV0)


class TestBrowserUseCDPTransport:
    """Tests for BrowserUseCDPTransport."""

    @pytest.mark.asyncio
    async def test_send_translates_method(self) -> None:
        """Test that send correctly translates method to cdp-use pattern."""
        # Create mock cdp_client with send.Domain.method pattern
        mock_method = AsyncMock(return_value={"result": "success"})
        mock_domain = MagicMock()
        mock_domain.evaluate = mock_method

        mock_send = MagicMock()
        mock_send.Runtime = mock_domain

        mock_client = MagicMock()
        mock_client.send = mock_send

        transport = BrowserUseCDPTransport(mock_client, "session-123")
        result = await transport.send("Runtime.evaluate", {"expression": "1+1"})

        # Verify the method was called correctly
        mock_method.assert_called_once_with(
            params={"expression": "1+1"},
            session_id="session-123",
        )
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_send_invalid_method_format(self) -> None:
        """Test send raises on invalid method format."""
        mock_client = MagicMock()
        transport = BrowserUseCDPTransport(mock_client, "session-123")

        with pytest.raises(ValueError, match="Invalid CDP method format"):
            await transport.send("InvalidMethod")

    @pytest.mark.asyncio
    async def test_send_unknown_domain(self) -> None:
        """Test send raises on unknown domain."""
        mock_send = MagicMock()
        mock_send.UnknownDomain = None

        mock_client = MagicMock()
        mock_client.send = mock_send

        transport = BrowserUseCDPTransport(mock_client, "session-123")

        with pytest.raises(ValueError, match="Unknown CDP domain"):
            await transport.send("UnknownDomain.method")


class TestBrowserUseAdapter:
    """Tests for BrowserUseAdapter."""

    def test_api_key_returns_none(self) -> None:
        """Test api_key property returns None."""
        mock_session = MagicMock()
        adapter = BrowserUseAdapter(mock_session)
        assert adapter.api_key is None

    def test_api_url_returns_none(self) -> None:
        """Test api_url property returns None."""
        mock_session = MagicMock()
        adapter = BrowserUseAdapter(mock_session)
        assert adapter.api_url is None

    @pytest.mark.asyncio
    async def test_create_backend(self) -> None:
        """Test create_backend creates CDPBackendV0."""
        # Create mock CDP session
        mock_cdp_session = MagicMock()
        mock_cdp_session.cdp_client = MagicMock()
        mock_cdp_session.session_id = "session-123"

        # Create mock browser session
        mock_session = MagicMock()
        mock_session.get_or_create_cdp_session = AsyncMock(return_value=mock_cdp_session)

        adapter = BrowserUseAdapter(mock_session)
        backend = await adapter.create_backend()

        assert isinstance(backend, CDPBackendV0)
        mock_session.get_or_create_cdp_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_backend_caches_result(self) -> None:
        """Test create_backend returns same instance on repeated calls."""
        mock_cdp_session = MagicMock()
        mock_cdp_session.cdp_client = MagicMock()
        mock_cdp_session.session_id = "session-123"

        mock_session = MagicMock()
        mock_session.get_or_create_cdp_session = AsyncMock(return_value=mock_cdp_session)

        adapter = BrowserUseAdapter(mock_session)

        backend1 = await adapter.create_backend()
        backend2 = await adapter.create_backend()

        assert backend1 is backend2
        # Should only create once
        assert mock_session.get_or_create_cdp_session.call_count == 1

    @pytest.mark.asyncio
    async def test_create_backend_no_cdp_method(self) -> None:
        """Test create_backend raises if session lacks CDP support."""
        mock_session = MagicMock(spec=[])  # No get_or_create_cdp_session

        adapter = BrowserUseAdapter(mock_session)

        with pytest.raises(RuntimeError, match="does not have get_or_create_cdp_session"):
            await adapter.create_backend()

    @pytest.mark.asyncio
    async def test_get_page_async(self) -> None:
        """Test get_page_async returns page from session."""
        mock_page = MagicMock()
        mock_session = MagicMock()
        mock_session.get_current_page = AsyncMock(return_value=mock_page)

        adapter = BrowserUseAdapter(mock_session)
        page = await adapter.get_page_async()

        assert page is mock_page


class TestBackendAgnosticActions:
    """Tests for backend-agnostic action functions."""

    @pytest.fixture
    def transport(self) -> MockCDPTransport:
        """Create mock transport."""
        return MockCDPTransport()

    @pytest.fixture
    def backend(self, transport: MockCDPTransport) -> CDPBackendV0:
        """Create backend with mock transport."""
        return CDPBackendV0(transport)

    @pytest.mark.asyncio
    async def test_click_with_tuple(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test click with (x, y) tuple."""
        result = await click(backend, (100, 200))

        assert isinstance(result, ActionResult)
        assert result.success is True

        # Should have mouse move + mouse click (press + release)
        mouse_events = [c for c in transport.calls if c[0] == "Input.dispatchMouseEvent"]
        assert len(mouse_events) == 3  # move, press, release

    @pytest.mark.asyncio
    async def test_click_with_bbox(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test click with BBox (clicks center)."""
        bbox = BBox(x=100, y=200, width=50, height=30)
        result = await click(backend, bbox)

        assert result.success is True

        # Find the click event
        press_events = [
            c
            for c in transport.calls
            if c[0] == "Input.dispatchMouseEvent" and c[1]["type"] == "mousePressed"
        ]
        assert len(press_events) == 1
        # Should click at center: (100 + 25, 200 + 15) = (125, 215)
        assert press_events[0][1]["x"] == 125
        assert press_events[0][1]["y"] == 215

    @pytest.mark.asyncio
    async def test_click_with_dict(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test click with dict containing x, y."""
        result = await click(backend, {"x": 150, "y": 250})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_click_double(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test double-click."""
        result = await click(backend, (100, 200), click_count=2)

        assert result.success is True

        # Check clickCount parameter
        press_events = [
            c
            for c in transport.calls
            if c[0] == "Input.dispatchMouseEvent" and c[1]["type"] == "mousePressed"
        ]
        assert press_events[0][1]["clickCount"] == 2

    @pytest.mark.asyncio
    async def test_type_text_simple(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test typing text."""
        result = await type_text(backend, "Hi")

        assert isinstance(result, ActionResult)
        assert result.success is True

        # Check key events were dispatched
        key_events = [c for c in transport.calls if c[0] == "Input.dispatchKeyEvent"]
        assert len(key_events) == 6  # 2 chars * 3 events each

    @pytest.mark.asyncio
    async def test_type_text_with_target(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test typing text with click target."""
        result = await type_text(backend, "test", target=(100, 200))

        assert result.success is True

        # Should have click + key events
        mouse_events = [c for c in transport.calls if c[0] == "Input.dispatchMouseEvent"]
        key_events = [c for c in transport.calls if c[0] == "Input.dispatchKeyEvent"]
        assert len(mouse_events) >= 2  # At least press + release
        assert len(key_events) == 12  # 4 chars * 3 events

    @pytest.mark.asyncio
    async def test_scroll_down(self, backend: CDPBackendV0, transport: MockCDPTransport) -> None:
        """Test scrolling down."""
        # Set up viewport for default coordinates
        transport.set_response(
            "Runtime.evaluate",
            {
                "result": {
                    "type": "object",
                    "value": {"width": 1920, "height": 1080},
                }
            },
        )

        result = await scroll(backend, delta_y=300)

        assert result.success is True

        wheel_events = [
            c
            for c in transport.calls
            if c[0] == "Input.dispatchMouseEvent" and c[1].get("type") == "mouseWheel"
        ]
        assert len(wheel_events) == 1
        assert wheel_events[0][1]["deltaY"] == 300

    @pytest.mark.asyncio
    async def test_scroll_at_position(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test scrolling at specific position."""
        result = await scroll(backend, delta_y=200, target=(500, 300))

        assert result.success is True

        wheel_events = [
            c
            for c in transport.calls
            if c[0] == "Input.dispatchMouseEvent" and c[1].get("type") == "mouseWheel"
        ]
        assert wheel_events[0][1]["x"] == 500
        assert wheel_events[0][1]["y"] == 300

    @pytest.mark.asyncio
    async def test_wait_for_stable_success(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test wait_for_stable with immediate success."""
        transport.set_response(
            "Runtime.evaluate",
            {"result": {"type": "string", "value": "complete"}},
        )

        result = await wait_for_stable(backend, state="complete", timeout_ms=1000)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_wait_for_stable_timeout(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test wait_for_stable timeout."""
        transport.set_response(
            "Runtime.evaluate",
            {"result": {"type": "string", "value": "loading"}},
        )

        result = await wait_for_stable(backend, state="complete", timeout_ms=200)

        assert result.success is False
        assert result.error["code"] == "timeout"


class TestPlaywrightBackend:
    """Tests for PlaywrightBackend wrapper."""

    def test_implements_protocol(self) -> None:
        """Verify PlaywrightBackend implements BrowserBackendV0."""
        mock_page = MagicMock()
        backend = PlaywrightBackend(mock_page)
        assert isinstance(backend, BrowserBackendV0)

    def test_page_property(self) -> None:
        """Test page property returns underlying page."""
        mock_page = MagicMock()
        backend = PlaywrightBackend(mock_page)
        assert backend.page is mock_page

    @pytest.mark.asyncio
    async def test_refresh_page_info(self) -> None:
        """Test refresh_page_info calls page.evaluate."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(
            return_value={
                "width": 1920,
                "height": 1080,
                "scroll_x": 0,
                "scroll_y": 100,
                "content_width": 1920,
                "content_height": 5000,
            }
        )

        backend = PlaywrightBackend(mock_page)
        info = await backend.refresh_page_info()

        assert isinstance(info, ViewportInfo)
        assert info.width == 1920
        assert info.scroll_y == 100

    @pytest.mark.asyncio
    async def test_eval(self) -> None:
        """Test eval calls page.evaluate."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=42)

        backend = PlaywrightBackend(mock_page)
        result = await backend.eval("1 + 1")

        assert result == 42

    @pytest.mark.asyncio
    async def test_mouse_click(self) -> None:
        """Test mouse_click calls page.mouse.click."""
        mock_mouse = AsyncMock()
        mock_page = MagicMock()
        mock_page.mouse = mock_mouse

        backend = PlaywrightBackend(mock_page)
        await backend.mouse_click(100, 200, button="left", click_count=1)

        mock_mouse.click.assert_called_once_with(100, 200, button="left", click_count=1)

    @pytest.mark.asyncio
    async def test_type_text(self) -> None:
        """Test type_text calls page.keyboard.type."""
        mock_keyboard = AsyncMock()
        mock_page = MagicMock()
        mock_page.keyboard = mock_keyboard

        backend = PlaywrightBackend(mock_page)
        await backend.type_text("Hello")

        mock_keyboard.type.assert_called_once_with("Hello")

    @pytest.mark.asyncio
    async def test_screenshot_png(self) -> None:
        """Test screenshot_png calls page.screenshot."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")

        backend = PlaywrightBackend(mock_page)
        result = await backend.screenshot_png()

        assert result.startswith(b"\x89PNG")
        mock_page.screenshot.assert_called_once_with(type="png")


class TestCachedSnapshot:
    """Tests for CachedSnapshot caching behavior."""

    @pytest.fixture
    def mock_backend(self) -> MagicMock:
        """Create mock backend."""
        backend = MagicMock()
        backend.eval = AsyncMock()
        return backend

    def test_initial_state(self, mock_backend: MagicMock) -> None:
        """Test initial cache state."""
        cache = CachedSnapshot(mock_backend, max_age_ms=2000)

        assert cache.is_cached is False
        assert cache.age_ms == float("inf")

    def test_invalidate(self, mock_backend: MagicMock) -> None:
        """Test cache invalidation."""
        cache = CachedSnapshot(mock_backend)
        cache._cached = MagicMock()  # Simulate cached snapshot
        cache._cached_at = time.time()

        assert cache.is_cached is True

        cache.invalidate()

        assert cache.is_cached is False
        assert cache.age_ms == float("inf")

    def test_staleness_by_age(self, mock_backend: MagicMock) -> None:
        """Test cache staleness detection."""
        cache = CachedSnapshot(mock_backend, max_age_ms=100)

        # Simulate old cache
        cache._cached = MagicMock()
        cache._cached_at = time.time() - 0.2  # 200ms ago

        assert cache._is_stale() is True

    def test_fresh_cache(self, mock_backend: MagicMock) -> None:
        """Test fresh cache detection."""
        cache = CachedSnapshot(mock_backend, max_age_ms=2000)

        # Simulate fresh cache
        cache._cached = MagicMock()
        cache._cached_at = time.time()

        assert cache._is_stale() is False


class TestCoordinateResolution:
    """Test coordinate resolution in actions."""

    @pytest.mark.asyncio
    async def test_bbox_center_calculation(self) -> None:
        """Test BBox center calculation."""
        from sentience.backends.actions import _resolve_coordinates

        bbox = BBox(x=100, y=200, width=50, height=30)
        x, y = _resolve_coordinates(bbox)

        assert x == 125  # 100 + 50/2
        assert y == 215  # 200 + 30/2

    @pytest.mark.asyncio
    async def test_dict_with_dimensions(self) -> None:
        """Test dict with width/height computes center."""
        from sentience.backends.actions import _resolve_coordinates

        target = {"x": 100, "y": 200, "width": 50, "height": 30}
        x, y = _resolve_coordinates(target)

        assert x == 125
        assert y == 215

    @pytest.mark.asyncio
    async def test_dict_without_dimensions(self) -> None:
        """Test dict without width/height uses x/y directly."""
        from sentience.backends.actions import _resolve_coordinates

        target = {"x": 150, "y": 250}
        x, y = _resolve_coordinates(target)

        assert x == 150
        assert y == 250

    @pytest.mark.asyncio
    async def test_tuple_passthrough(self) -> None:
        """Test tuple passes through unchanged."""
        from sentience.backends.actions import _resolve_coordinates

        x, y = _resolve_coordinates((300, 400))

        assert x == 300
        assert y == 400
