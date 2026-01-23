"""
Playwright backend implementation for BrowserBackend protocol.

This wraps existing SentienceBrowser/AsyncSentienceBrowser to provide
a unified interface, enabling code that works with both browser-use
(CDPBackendV0) and native Playwright (PlaywrightBackend).

Usage:
    from sentience import SentienceBrowserAsync
    from sentience.backends import PlaywrightBackend, snapshot_from_backend

    browser = SentienceBrowserAsync()
    await browser.start()
    await browser.goto("https://example.com")

    # Create backend from existing browser
    backend = PlaywrightBackend(browser.page)

    # Use backend-agnostic functions
    snap = await snapshot_from_backend(backend)
    await click(backend, element.bbox)
"""

import asyncio
import inspect
import mimetypes
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .protocol import BrowserBackend, LayoutMetrics, ViewportInfo

if TYPE_CHECKING:
    from playwright.async_api import Page as AsyncPage


class PlaywrightBackend:
    """
    Playwright-based implementation of BrowserBackend.

    Wraps a Playwright async Page to provide the standard backend interface.
    This enables using backend-agnostic actions with existing SentienceBrowser code.
    """

    def __init__(self, page: "AsyncPage") -> None:
        """
        Initialize Playwright backend.

        Args:
            page: Playwright async Page object
        """
        self._page = page
        self._cached_viewport: ViewportInfo | None = None
        self._downloads: list[dict[str, Any]] = []

        # Best-effort download tracking (does not change behavior unless a download occurs).
        # pylint: disable=broad-exception-caught
        try:
            result = self._page.on(
                "download", lambda d: asyncio.create_task(self._track_download(d))
            )
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop().create_task(result)
                except RuntimeError:
                    pass
        except Exception:
            pass

    @property
    def downloads(self) -> list[dict[str, Any]]:
        """Best-effort Playwright download records."""
        return self._downloads

    async def _track_download(self, download: Any) -> None:
        rec: dict[str, Any] = {
            "status": "started",
            "suggested_filename": getattr(download, "suggested_filename", None),
            "url": getattr(download, "url", None),
        }
        self._downloads.append(rec)
        try:
            # Wait for completion and capture path if Playwright provides it.
            p = await download.path()
            if p:
                rec["status"] = "completed"
                rec["path"] = str(p)
                rec["filename"] = Path(str(p)).name
                try:
                    rec["size_bytes"] = int(os.path.getsize(str(p)))
                except Exception:
                    pass
                try:
                    mt, _enc = mimetypes.guess_type(str(p))
                    if mt:
                        rec["mime_type"] = mt
                except Exception:
                    pass
            else:
                rec["status"] = "completed"
        except Exception as e:
            rec["status"] = "failed"
            rec["error"] = str(e)

    @property
    def page(self) -> "AsyncPage":
        """Access the underlying Playwright page."""
        return self._page

    async def refresh_page_info(self) -> ViewportInfo:
        """Cache viewport + scroll offsets; cheap & safe to call often."""
        result = await self._page.evaluate(
            """
            (() => ({
                width: window.innerWidth,
                height: window.innerHeight,
                scroll_x: window.scrollX,
                scroll_y: window.scrollY,
                content_width: document.documentElement.scrollWidth,
                content_height: document.documentElement.scrollHeight
            }))()
        """
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
        """Evaluate JavaScript expression in page context."""
        return await self._page.evaluate(expression)

    async def call(
        self,
        function_declaration: str,
        args: list[Any] | None = None,
    ) -> Any:
        """Call JavaScript function with arguments."""
        if args:
            return await self._page.evaluate(function_declaration, *args)
        return await self._page.evaluate(f"({function_declaration})()")

    async def get_layout_metrics(self) -> LayoutMetrics:
        """Get page layout metrics."""
        # Playwright doesn't expose CDP directly in the same way,
        # so we approximate using JavaScript
        result = await self._page.evaluate(
            """
            (() => ({
                viewport_x: window.scrollX,
                viewport_y: window.scrollY,
                viewport_width: window.innerWidth,
                viewport_height: window.innerHeight,
                content_width: document.documentElement.scrollWidth,
                content_height: document.documentElement.scrollHeight,
                device_scale_factor: window.devicePixelRatio || 1
            }))()
        """
        )

        return LayoutMetrics(
            viewport_x=result.get("viewport_x", 0),
            viewport_y=result.get("viewport_y", 0),
            viewport_width=result.get("viewport_width", 0),
            viewport_height=result.get("viewport_height", 0),
            content_width=result.get("content_width", 0),
            content_height=result.get("content_height", 0),
            device_scale_factor=result.get("device_scale_factor", 1.0),
        )

    async def screenshot_png(self) -> bytes:
        """Capture viewport screenshot as PNG bytes."""
        return await self._page.screenshot(type="png")

    async def screenshot_jpeg(self, quality: int | None = None) -> bytes:
        """Capture viewport screenshot as JPEG bytes."""
        q = 80 if quality is None else max(1, min(int(quality), 100))
        return await self._page.screenshot(type="jpeg", quality=q)

    async def mouse_move(self, x: float, y: float) -> None:
        """Move mouse to viewport coordinates."""
        await self._page.mouse.move(x, y)

    async def mouse_click(
        self,
        x: float,
        y: float,
        button: Literal["left", "right", "middle"] = "left",
        click_count: int = 1,
    ) -> None:
        """Click at viewport coordinates."""
        await self._page.mouse.click(x, y, button=button, click_count=click_count)

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

        await self._page.mouse.wheel(0, delta_y)

    async def type_text(self, text: str) -> None:
        """Type text using keyboard input."""
        await self._page.keyboard.type(text)

    async def wait_ready_state(
        self,
        state: Literal["interactive", "complete"] = "interactive",
        timeout_ms: int = 15000,
    ) -> None:
        """Wait for document.readyState to reach target state."""
        acceptable_states = {"complete"} if state == "complete" else {"interactive", "complete"}

        start = time.monotonic()
        timeout_sec = timeout_ms / 1000.0

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_sec:
                raise TimeoutError(
                    f"Timed out waiting for document.readyState='{state}' " f"after {timeout_ms}ms"
                )

            current_state = await self._page.evaluate("document.readyState")
            if current_state in acceptable_states:
                return

            await asyncio.sleep(0.1)

    async def get_url(self) -> str:
        """Get current page URL."""
        return self._page.url


# Verify protocol compliance at import time
assert isinstance(PlaywrightBackend.__new__(PlaywrightBackend), BrowserBackend)
