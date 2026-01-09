"""
Tests for the backends module.

These tests verify the CDP backend implementation works correctly
without requiring a real browser (using mocked CDP transport).
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sentience.backends import (
    BrowserBackendV0,
    BrowserUseAdapter,
    BrowserUseCDPTransport,
    CDPBackendV0,
    CDPTransport,
    LayoutMetrics,
    ViewportInfo,
)


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
    async def test_eval(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
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
    async def test_eval_exception(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
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
    async def test_screenshot_png(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
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
    async def test_mouse_move(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
        """Test mouse_move dispatches mouseMoved event."""
        await backend.mouse_move(100, 200)

        assert len(transport.calls) == 1
        method, params = transport.calls[0]
        assert method == "Input.dispatchMouseEvent"
        assert params["type"] == "mouseMoved"
        assert params["x"] == 100
        assert params["y"] == 200

    @pytest.mark.asyncio
    async def test_mouse_click(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
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
    async def test_wheel(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
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
    async def test_type_text(
        self, backend: CDPBackendV0, transport: MockCDPTransport
    ) -> None:
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
        mock_session.get_or_create_cdp_session = AsyncMock(
            return_value=mock_cdp_session
        )

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
        mock_session.get_or_create_cdp_session = AsyncMock(
            return_value=mock_cdp_session
        )

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
