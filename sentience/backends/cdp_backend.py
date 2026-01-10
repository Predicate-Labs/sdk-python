"""
CDP Backend implementation for browser-use integration.

This module provides CDPBackendV0, which implements BrowserBackendV0 protocol
using Chrome DevTools Protocol (CDP) commands.

Usage with browser-use:
    from browser_use import BrowserSession
    from sentience.backends import CDPBackendV0
    from sentience.backends.browser_use_adapter import BrowserUseAdapter

    session = BrowserSession(...)
    await session.start()

    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Now use backend for Sentience operations
    viewport = await backend.refresh_page_info()
    await backend.mouse_click(100, 200)
"""

import asyncio
import base64
import time
from typing import Any, Literal, Protocol, runtime_checkable

from .protocol_v0 import BrowserBackendV0, LayoutMetrics, ViewportInfo


@runtime_checkable
class CDPTransport(Protocol):
    """
    Protocol for CDP transport layer.

    This abstracts the actual CDP communication, allowing different
    implementations (browser-use, Playwright CDP, raw WebSocket).
    """

    async def send(self, method: str, params: dict | None = None) -> dict:
        """
        Send a CDP command and return the result.

        Args:
            method: CDP method name, e.g., "Runtime.evaluate"
            params: Method parameters

        Returns:
            CDP response dict
        """
        ...


class CDPBackendV0:
    """
    CDP-based implementation of BrowserBackendV0.

    This backend uses CDP commands to interact with the browser,
    making it compatible with browser-use's CDP client.
    """

    def __init__(self, transport: CDPTransport) -> None:
        """
        Initialize CDP backend.

        Args:
            transport: CDP transport for sending commands
        """
        self._transport = transport
        self._cached_viewport: ViewportInfo | None = None
        self._execution_context_id: int | None = None

    async def _get_execution_context(self) -> int:
        """Get or create execution context ID for Runtime.callFunctionOn."""
        if self._execution_context_id is not None:
            return self._execution_context_id

        # Enable Runtime domain if not already enabled
        try:
            await self._transport.send("Runtime.enable")
        except Exception:
            pass  # May already be enabled

        # Get the main frame's execution context
        result = await self._transport.send(
            "Runtime.evaluate",
            {
                "expression": "1",
                "returnByValue": True,
            },
        )

        # Extract context ID from the result
        if "executionContextId" in result:
            self._execution_context_id = result["executionContextId"]
        else:
            # Fallback: use context ID 1 (main frame)
            self._execution_context_id = 1

        return self._execution_context_id

    async def refresh_page_info(self) -> ViewportInfo:
        """Cache viewport + scroll offsets; cheap & safe to call often."""
        result = await self.eval(
            """(() => ({
                width: window.innerWidth,
                height: window.innerHeight,
                scroll_x: window.scrollX,
                scroll_y: window.scrollY,
                content_width: document.documentElement.scrollWidth,
                content_height: document.documentElement.scrollHeight
            }))()"""
        )

        self._cached_viewport = ViewportInfo(
            width=result.get("width", 0),
            height=result.get("height", 0),
            scroll_x=result.get("scroll_x", 0),
            scroll_y=result.get("scroll_y", 0),
            content_width=result.get("content_width"),
            content_height=result.get("content_height"),
        )
        return self._cached_viewport

    async def eval(self, expression: str) -> Any:
        """Evaluate JavaScript expression using Runtime.evaluate."""
        result = await self._transport.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )

        # Check for exceptions
        if "exceptionDetails" in result:
            exc = result["exceptionDetails"]
            text = exc.get("text", "Unknown error")
            raise RuntimeError(f"JavaScript evaluation failed: {text}")

        # Extract value from result
        if "result" in result:
            res = result["result"]
            if res.get("type") == "undefined":
                return None
            return res.get("value")

        return None

    async def call(
        self,
        function_declaration: str,
        args: list[Any] | None = None,
    ) -> Any:
        """Call JavaScript function using Runtime.callFunctionOn."""
        # Build call arguments
        call_args = []
        if args:
            for arg in args:
                if arg is None:
                    call_args.append({"value": None})
                elif isinstance(arg, bool):
                    call_args.append({"value": arg})
                elif isinstance(arg, (int, float)):
                    call_args.append({"value": arg})
                elif isinstance(arg, str):
                    call_args.append({"value": arg})
                elif isinstance(arg, dict):
                    call_args.append({"value": arg})
                elif isinstance(arg, list):
                    call_args.append({"value": arg})
                else:
                    # Serialize complex objects to JSON
                    call_args.append({"value": str(arg)})

        # We need an object ID to call function on
        # Use globalThis (window) as the target
        global_result = await self._transport.send(
            "Runtime.evaluate",
            {
                "expression": "globalThis",
                "returnByValue": False,
            },
        )

        object_id = global_result.get("result", {}).get("objectId")
        if not object_id:
            # Fallback: evaluate the function directly
            if args:
                args_json = ", ".join(repr(a) if isinstance(a, str) else str(a) for a in args)
                expression = f"({function_declaration})({args_json})"
            else:
                expression = f"({function_declaration})()"
            return await self.eval(expression)

        result = await self._transport.send(
            "Runtime.callFunctionOn",
            {
                "functionDeclaration": function_declaration,
                "objectId": object_id,
                "arguments": call_args,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )

        # Check for exceptions
        if "exceptionDetails" in result:
            exc = result["exceptionDetails"]
            text = exc.get("text", "Unknown error")
            raise RuntimeError(f"JavaScript call failed: {text}")

        # Extract value from result
        if "result" in result:
            res = result["result"]
            if res.get("type") == "undefined":
                return None
            return res.get("value")

        return None

    async def get_layout_metrics(self) -> LayoutMetrics:
        """Get page layout metrics using Page.getLayoutMetrics."""
        result = await self._transport.send("Page.getLayoutMetrics")

        # Extract metrics from result
        layout_viewport = result.get("layoutViewport", {})
        content_size = result.get("contentSize", {})
        visual_viewport = result.get("visualViewport", {})

        return LayoutMetrics(
            viewport_x=visual_viewport.get("pageX", 0),
            viewport_y=visual_viewport.get("pageY", 0),
            viewport_width=visual_viewport.get(
                "clientWidth", layout_viewport.get("clientWidth", 0)
            ),
            viewport_height=visual_viewport.get(
                "clientHeight", layout_viewport.get("clientHeight", 0)
            ),
            content_width=content_size.get("width", 0),
            content_height=content_size.get("height", 0),
            device_scale_factor=visual_viewport.get("scale", 1.0),
        )

    async def screenshot_png(self) -> bytes:
        """Capture viewport screenshot as PNG bytes."""
        result = await self._transport.send(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": False,
            },
        )

        data = result.get("data", "")
        return base64.b64decode(data)

    async def mouse_move(self, x: float, y: float) -> None:
        """Move mouse to viewport coordinates."""
        await self._transport.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": x,
                "y": y,
            },
        )

    async def mouse_click(
        self,
        x: float,
        y: float,
        button: Literal["left", "right", "middle"] = "left",
        click_count: int = 1,
    ) -> None:
        """Click at viewport coordinates."""
        # Mouse down
        await self._transport.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            },
        )

        # Small delay between press and release
        await asyncio.sleep(0.05)

        # Mouse up
        await self._transport.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            },
        )

    async def wheel(
        self,
        delta_y: float,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        """Scroll using mouse wheel."""
        # Get viewport center if coordinates not provided
        if x is None or y is None:
            if self._cached_viewport is None:
                await self.refresh_page_info()
            assert self._cached_viewport is not None
            x = x if x is not None else self._cached_viewport.width / 2
            y = y if y is not None else self._cached_viewport.height / 2

        await self._transport.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": x,
                "y": y,
                "deltaX": 0,
                "deltaY": delta_y,
            },
        )

    async def type_text(self, text: str) -> None:
        """Type text using keyboard input."""
        for char in text:
            # Key down
            await self._transport.send(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyDown",
                    "text": char,
                },
            )

            # Char event (for text input)
            await self._transport.send(
                "Input.dispatchKeyEvent",
                {
                    "type": "char",
                    "text": char,
                },
            )

            # Key up
            await self._transport.send(
                "Input.dispatchKeyEvent",
                {
                    "type": "keyUp",
                    "text": char,
                },
            )

            # Small delay between characters
            await asyncio.sleep(0.01)

    async def wait_ready_state(
        self,
        state: Literal["interactive", "complete"] = "interactive",
        timeout_ms: int = 15000,
    ) -> None:
        """Wait for document.readyState using polling."""
        start = time.monotonic()
        timeout_sec = timeout_ms / 1000.0

        # Map state to acceptable states
        acceptable_states = {"complete"} if state == "complete" else {"interactive", "complete"}

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_sec:
                raise TimeoutError(
                    f"Timed out waiting for document.readyState='{state}' " f"after {timeout_ms}ms"
                )

            current_state = await self.eval("document.readyState")
            if current_state in acceptable_states:
                return

            # Poll every 100ms
            await asyncio.sleep(0.1)
