"""
v0 BrowserBackend Protocol - Minimal interface for browser-use integration.

This protocol defines the minimal interface required to:
- Take Sentience snapshots (DOM/geometry via extension)
- Compute viewport-coord clicks
- Scroll + re-snapshot + click
- Stabilize after action

No navigation API required (browser-use already handles navigation).

Design principle: Keep it so small that nothing can break.
"""

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel


class ViewportInfo(BaseModel):
    """Viewport and scroll position information."""

    width: int
    height: int
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    content_width: float | None = None
    content_height: float | None = None


class LayoutMetrics(BaseModel):
    """Page layout metrics from CDP Page.getLayoutMetrics."""

    # Viewport dimensions
    viewport_x: float = 0.0
    viewport_y: float = 0.0
    viewport_width: float = 0.0
    viewport_height: float = 0.0

    # Content dimensions (scrollable area)
    content_width: float = 0.0
    content_height: float = 0.0

    # Device scale factor
    device_scale_factor: float = 1.0


@runtime_checkable
class BrowserBackend(Protocol):
    """
    Minimal backend protocol for v0 proof-of-concept.

    This is enough to:
    - Take Sentience snapshots (DOM/geometry via extension)
    - Execute JavaScript for element interaction
    - Perform mouse operations (move, click, scroll)
    - Wait for page stability

    Implementers:
    - CDPBackendV0: For browser-use integration via CDP
    - PlaywrightBackend: Wrapper around existing SentienceBrowser (future)
    """

    async def refresh_page_info(self) -> ViewportInfo:
        """
        Cache viewport + scroll offsets + url; cheap & safe to call often.

        Returns:
            ViewportInfo with current viewport state
        """
        ...

    async def eval(self, expression: str) -> Any:
        """
        Evaluate JavaScript expression in page context.

        Uses CDP Runtime.evaluate with returnByValue=True.

        Args:
            expression: JavaScript expression to evaluate

        Returns:
            Result value (JSON-serializable)
        """
        ...

    async def call(
        self,
        function_declaration: str,
        args: list[Any] | None = None,
    ) -> Any:
        """
        Call a JavaScript function with arguments.

        Uses CDP Runtime.callFunctionOn for safe argument passing.
        Safer than eval() for passing complex arguments.

        Args:
            function_declaration: JavaScript function body, e.g., "(x, y) => x + y"
            args: Arguments to pass to the function

        Returns:
            Result value (JSON-serializable)
        """
        ...

    async def get_layout_metrics(self) -> LayoutMetrics:
        """
        Get page layout metrics.

        Uses CDP Page.getLayoutMetrics to get viewport and content dimensions.

        Returns:
            LayoutMetrics with viewport and content size info
        """
        ...

    async def screenshot_png(self) -> bytes:
        """
        Capture viewport screenshot as PNG bytes.

        Uses CDP Page.captureScreenshot.

        Returns:
            PNG image bytes
        """
        ...

    async def screenshot_jpeg(self, quality: int | None = None) -> bytes:
        """
        Capture viewport screenshot as JPEG bytes.

        Args:
            quality: Optional JPEG quality (1-100)

        Returns:
            JPEG image bytes
        """
        ...

    async def mouse_move(self, x: float, y: float) -> None:
        """
        Move mouse to viewport coordinates.

        Uses CDP Input.dispatchMouseEvent with type="mouseMoved".

        Args:
            x: X coordinate in viewport
            y: Y coordinate in viewport
        """
        ...

    async def mouse_click(
        self,
        x: float,
        y: float,
        button: Literal["left", "right", "middle"] = "left",
        click_count: int = 1,
    ) -> None:
        """
        Click at viewport coordinates.

        Uses CDP Input.dispatchMouseEvent with mousePressed + mouseReleased.

        Args:
            x: X coordinate in viewport
            y: Y coordinate in viewport
            button: Mouse button to click
            click_count: Number of clicks (1 for single, 2 for double)
        """
        ...

    async def wheel(
        self,
        delta_y: float,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        """
        Scroll using mouse wheel.

        Uses CDP Input.dispatchMouseEvent with type="mouseWheel".

        Args:
            delta_y: Scroll amount (positive = down, negative = up)
            x: X coordinate for scroll (default: viewport center)
            y: Y coordinate for scroll (default: viewport center)
        """
        ...

    async def type_text(self, text: str, delay_ms: float | None = None) -> None:
        """
        Type text using keyboard input.

        Uses CDP Input.dispatchKeyEvent for each character.

        Args:
            text: Text to type
            delay_ms: Optional delay between keystrokes in milliseconds.
                      If None, backend default behavior is used.
        """
        ...

    async def wait_ready_state(
        self,
        state: Literal["interactive", "complete"] = "interactive",
        timeout_ms: int = 15000,
    ) -> None:
        """
        Wait for document.readyState to reach target state.

        Uses polling instead of CDP events (no leak from unregistered listeners).

        Args:
            state: Target state ("interactive" or "complete")
            timeout_ms: Maximum time to wait in milliseconds

        Raises:
            TimeoutError: If state not reached within timeout
        """
        ...

    async def get_url(self) -> str:
        """
        Get current page URL.

        Returns:
            Current page URL (window.location.href)
        """
        ...
