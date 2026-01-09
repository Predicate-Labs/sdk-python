"""
Backend-agnostic actions for browser-use integration.

These actions work with any BrowserBackendV0 implementation,
enabling Sentience grounding with browser-use or other frameworks.

Usage with browser-use:
    from sentience.backends import BrowserUseAdapter
    from sentience.backends.actions import click, type_text, scroll

    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Take snapshot and click element
    snap = await snapshot_from_backend(backend)
    element = find(snap, 'role=button[name="Submit"]')
    await click(backend, element.bbox)
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any, Literal

from ..models import ActionResult, BBox, Snapshot

if TYPE_CHECKING:
    from .protocol_v0 import BrowserBackendV0


async def click(
    backend: "BrowserBackendV0",
    target: BBox | dict[str, float] | tuple[float, float],
    button: Literal["left", "right", "middle"] = "left",
    click_count: int = 1,
    move_first: bool = True,
) -> ActionResult:
    """
    Click at coordinates using the backend.

    Args:
        backend: BrowserBackendV0 implementation
        target: Click target - BBox (clicks center), dict with x/y, or (x, y) tuple
        button: Mouse button to click
        click_count: Number of clicks (1=single, 2=double)
        move_first: Whether to move mouse to position before clicking

    Returns:
        ActionResult with success status

    Example:
        # Click at coordinates
        await click(backend, (100, 200))

        # Click element bbox center
        await click(backend, element.bbox)

        # Double-click
        await click(backend, element.bbox, click_count=2)
    """
    start_time = time.time()

    # Resolve coordinates
    x, y = _resolve_coordinates(target)

    try:
        # Optional mouse move for hover effects
        if move_first:
            await backend.mouse_move(x, y)
            await asyncio.sleep(0.02)  # Brief pause for hover

        # Perform click
        await backend.mouse_click(x, y, button=button, click_count=click_count)

        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=True,
            duration_ms=duration_ms,
            outcome="dom_updated",
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=False,
            duration_ms=duration_ms,
            outcome="error",
            error={"code": "click_failed", "reason": str(e)},
        )


async def type_text(
    backend: "BrowserBackendV0",
    text: str,
    target: BBox | dict[str, float] | tuple[float, float] | None = None,
    clear_first: bool = False,
) -> ActionResult:
    """
    Type text, optionally clicking a target first.

    Args:
        backend: BrowserBackendV0 implementation
        text: Text to type
        target: Optional click target before typing (BBox, dict, or tuple)
        clear_first: If True, select all and delete before typing

    Returns:
        ActionResult with success status

    Example:
        # Type into focused element
        await type_text(backend, "Hello World")

        # Click input then type
        await type_text(backend, "search query", target=search_box.bbox)

        # Clear and type
        await type_text(backend, "new value", target=input.bbox, clear_first=True)
    """
    start_time = time.time()

    try:
        # Click target if provided
        if target is not None:
            x, y = _resolve_coordinates(target)
            await backend.mouse_click(x, y)
            await asyncio.sleep(0.05)  # Wait for focus

        # Clear existing content if requested
        if clear_first:
            # Select all (Ctrl+A / Cmd+A) and delete
            await backend.eval("document.execCommand('selectAll')")
            await asyncio.sleep(0.02)

        # Type the text
        await backend.type_text(text)

        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=True,
            duration_ms=duration_ms,
            outcome="dom_updated",
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=False,
            duration_ms=duration_ms,
            outcome="error",
            error={"code": "type_failed", "reason": str(e)},
        )


async def scroll(
    backend: "BrowserBackendV0",
    delta_y: float = 300,
    target: BBox | dict[str, float] | tuple[float, float] | None = None,
) -> ActionResult:
    """
    Scroll the page or element.

    Args:
        backend: BrowserBackendV0 implementation
        delta_y: Scroll amount (positive=down, negative=up)
        target: Optional position for scroll (defaults to viewport center)

    Returns:
        ActionResult with success status

    Example:
        # Scroll down 300px
        await scroll(backend, 300)

        # Scroll up 500px
        await scroll(backend, -500)

        # Scroll at specific position
        await scroll(backend, 200, target=(500, 300))
    """
    start_time = time.time()

    try:
        x: float | None = None
        y: float | None = None

        if target is not None:
            x, y = _resolve_coordinates(target)

        await backend.wheel(delta_y=delta_y, x=x, y=y)

        # Wait for scroll to settle
        await asyncio.sleep(0.1)

        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=True,
            duration_ms=duration_ms,
            outcome="dom_updated",
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=False,
            duration_ms=duration_ms,
            outcome="error",
            error={"code": "scroll_failed", "reason": str(e)},
        )


async def scroll_to_element(
    backend: "BrowserBackendV0",
    element_id: int,
    behavior: Literal["smooth", "instant", "auto"] = "instant",
    block: Literal["start", "center", "end", "nearest"] = "center",
) -> ActionResult:
    """
    Scroll element into view using JavaScript scrollIntoView.

    Args:
        backend: BrowserBackendV0 implementation
        element_id: Element ID from snapshot (requires sentience_registry)
        behavior: Scroll behavior
        block: Vertical alignment

    Returns:
        ActionResult with success status
    """
    start_time = time.time()

    try:
        scrolled = await backend.eval(f"""
            (() => {{
                const el = window.sentience_registry && window.sentience_registry[{element_id}];
                if (el && el.scrollIntoView) {{
                    el.scrollIntoView({{
                        behavior: '{behavior}',
                        block: '{block}',
                        inline: 'nearest'
                    }});
                    return true;
                }}
                return false;
            }})()
        """)

        # Wait for scroll animation
        wait_time = 0.3 if behavior == "smooth" else 0.05
        await asyncio.sleep(wait_time)

        duration_ms = int((time.time() - start_time) * 1000)

        if scrolled:
            return ActionResult(
                success=True,
                duration_ms=duration_ms,
                outcome="dom_updated",
            )
        else:
            return ActionResult(
                success=False,
                duration_ms=duration_ms,
                outcome="error",
                error={"code": "scroll_failed", "reason": "Element not found in registry"},
            )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=False,
            duration_ms=duration_ms,
            outcome="error",
            error={"code": "scroll_failed", "reason": str(e)},
        )


async def wait_for_stable(
    backend: "BrowserBackendV0",
    state: Literal["interactive", "complete"] = "complete",
    timeout_ms: int = 10000,
) -> ActionResult:
    """
    Wait for page to reach stable state.

    Args:
        backend: BrowserBackendV0 implementation
        state: Target document.readyState
        timeout_ms: Maximum wait time

    Returns:
        ActionResult with success status
    """
    start_time = time.time()

    try:
        await backend.wait_ready_state(state=state, timeout_ms=timeout_ms)

        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=True,
            duration_ms=duration_ms,
            outcome="dom_updated",
        )
    except TimeoutError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=False,
            duration_ms=duration_ms,
            outcome="error",
            error={"code": "timeout", "reason": str(e)},
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return ActionResult(
            success=False,
            duration_ms=duration_ms,
            outcome="error",
            error={"code": "wait_failed", "reason": str(e)},
        )


def _resolve_coordinates(
    target: BBox | dict[str, float] | tuple[float, float],
) -> tuple[float, float]:
    """
    Resolve target to (x, y) coordinates.

    - BBox: Returns center point
    - dict: Returns x, y keys (or center if width/height present)
    - tuple: Returns as-is
    """
    if isinstance(target, BBox):
        return (target.x + target.width / 2, target.y + target.height / 2)
    elif isinstance(target, tuple):
        return target
    elif isinstance(target, dict):
        # If has width/height, compute center
        if "width" in target and "height" in target:
            x = target.get("x", 0) + target["width"] / 2
            y = target.get("y", 0) + target["height"] / 2
            return (x, y)
        # Otherwise use x/y directly
        return (target.get("x", 0), target.get("y", 0))
    else:
        raise ValueError(f"Invalid target type: {type(target)}")
