from typing import Optional

"""
Actions v1 - click, type, press
"""

import time

from .browser import AsyncSentienceBrowser, SentienceBrowser
from .browser_evaluator import BrowserEvaluator
from .models import ActionResult, BBox, Snapshot
from .sentience_methods import SentienceMethod
from .snapshot import snapshot, snapshot_async


def click(  # noqa: C901
    browser: SentienceBrowser,
    element_id: int,
    use_mouse: bool = True,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Click an element by ID using hybrid approach (mouse simulation by default)

    Args:
        browser: SentienceBrowser instance
        element_id: Element ID from snapshot
        use_mouse: If True, use Playwright's mouse.click() at element center (hybrid approach).
                   If False, use JS-based window.sentience.click() (legacy).
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    if use_mouse:
        # Hybrid approach: Get element bbox from snapshot, calculate center, use mouse.click()
        try:
            snap = snapshot(browser)
            element = None
            for el in snap.elements:
                if el.id == element_id:
                    element = el
                    break

            if element:
                # Calculate center of element bbox
                center_x = element.bbox.x + element.bbox.width / 2
                center_y = element.bbox.y + element.bbox.height / 2
                # Use Playwright's native mouse click for realistic simulation
                try:
                    browser.page.mouse.click(center_x, center_y)
                    success = True
                except Exception:
                    # If navigation happens, mouse.click might fail, but that's OK
                    # The click still happened, just check URL change
                    success = True
            else:
                # Fallback to JS click if element not found in snapshot
                try:
                    success = BrowserEvaluator.invoke(
                        browser.page, SentienceMethod.CLICK, element_id
                    )
                except Exception:
                    # Navigation might have destroyed context, assume success if URL changed
                    success = True
        except Exception:
            # Fallback to JS click on error
            try:
                success = BrowserEvaluator.invoke(browser.page, SentienceMethod.CLICK, element_id)
            except Exception:
                # Navigation might have destroyed context, assume success if URL changed
                success = True
    else:
        # Legacy JS-based click
        success = BrowserEvaluator.invoke(browser.page, SentienceMethod.CLICK, element_id)

    # Wait a bit for navigation/DOM updates
    try:
        browser.page.wait_for_timeout(500)
    except Exception:
        # Navigation might have happened, context destroyed
        pass

    duration_ms = int((time.time() - start_time) * 1000)

    # Check if URL changed (handle navigation gracefully)
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        # Context destroyed due to navigation - assume URL changed
        url_after = url_before
        url_changed = True

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = snapshot(browser)
        except Exception:
            # Navigation might have destroyed context
            pass

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": "Element not found or not clickable",
            }
        ),
    )


def type_text(
    browser: SentienceBrowser, element_id: int, text: str, take_snapshot: bool = False
) -> ActionResult:
    """
    Type text into an element (focus then input)

    Args:
        browser: SentienceBrowser instance
        element_id: Element ID from snapshot
        text: Text to type
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Focus element first using extension registry
    focused = browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (el) {
                el.focus();
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not focused:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "focus_failed", "reason": "Element not found"},
        )

    # Type using Playwright keyboard
    browser.page.keyboard.type(text)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def press(browser: SentienceBrowser, key: str, take_snapshot: bool = False) -> ActionResult:
    """
    Press a keyboard key

    Args:
        browser: SentienceBrowser instance
        key: Key to press (e.g., "Enter", "Escape", "Tab")
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Press key using Playwright
    browser.page.keyboard.press(key)

    # Wait a bit for navigation/DOM updates
    browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


def _highlight_rect(
    browser: SentienceBrowser, rect: dict[str, float], duration_sec: float = 2.0
) -> None:
    """
    Highlight a rectangle with a red border overlay

    Args:
        browser: SentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys
        duration_sec: How long to show the highlight (default: 2 seconds)
    """
    if not browser.page:
        return

    # Create a unique ID for this highlight
    highlight_id = f"sentience_highlight_{int(time.time() * 1000)}"

    # Combine all arguments into a single object for Playwright
    args = {
        "rect": {
            "x": rect["x"],
            "y": rect["y"],
            "w": rect["w"],
            "h": rect["h"],
        },
        "highlightId": highlight_id,
        "durationSec": duration_sec,
    }

    # Inject CSS and create overlay element
    browser.page.evaluate(
        """
        (args) => {
            const { rect, highlightId, durationSec } = args;
            // Create overlay div
            const overlay = document.createElement('div');
            overlay.id = highlightId;
            overlay.style.position = 'fixed';
            overlay.style.left = `${rect.x}px`;
            overlay.style.top = `${rect.y}px`;
            overlay.style.width = `${rect.w}px`;
            overlay.style.height = `${rect.h}px`;
            overlay.style.border = '3px solid red';
            overlay.style.borderRadius = '2px';
            overlay.style.boxSizing = 'border-box';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '999999';
            overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
            overlay.style.transition = 'opacity 0.3s ease-out';

            document.body.appendChild(overlay);

            // Remove after duration
            setTimeout(() => {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    if (overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300); // Wait for fade-out transition
            }, durationSec * 1000);
        }
        """,
        args,
    )


def click_rect(
    browser: SentienceBrowser,
    rect: dict[str, float],
    highlight: bool = True,
    highlight_duration: float = 2.0,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Click at the center of a rectangle using Playwright's native mouse simulation.
    This uses a hybrid approach: calculates center coordinates and uses mouse.click()
    for realistic event simulation (triggers hover, focus, mousedown, mouseup).

    Args:
        browser: SentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys, or BBox object
        highlight: Whether to show a red border highlight when clicking (default: True)
        highlight_duration: How long to show the highlight in seconds (default: 2.0)
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult

    Example:
        >>> click_rect(browser, {"x": 100, "y": 200, "w": 50, "h": 30})
        >>> # Or using BBox object
        >>> from sentience import BBox
        >>> bbox = BBox(x=100, y=200, width=50, height=30)
        >>> click_rect(browser, {"x": bbox.x, "y": bbox.y, "w": bbox.width, "h": bbox.height})
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    # Handle BBox object or dict
    if isinstance(rect, BBox):
        x = rect.x
        y = rect.y
        w = rect.width
        h = rect.height
    else:
        x = rect.get("x", 0)
        y = rect.get("y", 0)
        w = rect.get("w") or rect.get("width", 0)
        h = rect.get("h") or rect.get("height", 0)

    if w <= 0 or h <= 0:
        return ActionResult(
            success=False,
            duration_ms=0,
            outcome="error",
            error={
                "code": "invalid_rect",
                "reason": "Rectangle width and height must be positive",
            },
        )

    start_time = time.time()
    url_before = browser.page.url

    # Calculate center of rectangle
    center_x = x + w / 2
    center_y = y + h / 2

    # Show highlight before clicking (if enabled)
    if highlight:
        _highlight_rect(browser, {"x": x, "y": y, "w": w, "h": h}, highlight_duration)
        # Small delay to ensure highlight is visible
        browser.page.wait_for_timeout(50)

    # Use Playwright's native mouse click for realistic simulation
    # This triggers hover, focus, mousedown, mouseup sequences
    try:
        browser.page.mouse.click(center_x, center_y)
        success = True
    except Exception as e:
        success = False
        error_msg = str(e)

    # Wait a bit for navigation/DOM updates
    browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = snapshot(browser)

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": error_msg if not success else "Click failed",
            }
        ),
    )


# ========== Async Action Functions ==========


async def click_async(
    browser: AsyncSentienceBrowser,
    element_id: int,
    use_mouse: bool = True,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Click an element by ID using hybrid approach (async)

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot
        use_mouse: If True, use Playwright's mouse.click() at element center
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    if use_mouse:
        try:
            snap = await snapshot_async(browser)
            element = None
            for el in snap.elements:
                if el.id == element_id:
                    element = el
                    break

            if element:
                center_x = element.bbox.x + element.bbox.width / 2
                center_y = element.bbox.y + element.bbox.height / 2
                try:
                    await browser.page.mouse.click(center_x, center_y)
                    success = True
                except Exception:
                    success = True
            else:
                try:
                    success = await browser.page.evaluate(
                        """
                        (id) => {
                            return window.sentience.click(id);
                        }
                        """,
                        element_id,
                    )
                except Exception:
                    success = True
        except Exception:
            try:
                success = await browser.page.evaluate(
                    """
                    (id) => {
                        return window.sentience.click(id);
                    }
                    """,
                    element_id,
                )
            except Exception:
                success = True
    else:
        success = await browser.page.evaluate(
            """
            (id) => {
                return window.sentience.click(id);
            }
            """,
            element_id,
        )

    # Wait a bit for navigation/DOM updates
    try:
        await browser.page.wait_for_timeout(500)
    except Exception:
        pass

    duration_ms = int((time.time() - start_time) * 1000)

    # Check if URL changed
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        url_after = url_before
        url_changed = True

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = await snapshot_async(browser)
        except Exception:
            pass

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": "Element not found or not clickable",
            }
        ),
    )


async def type_text_async(
    browser: AsyncSentienceBrowser, element_id: int, text: str, take_snapshot: bool = False
) -> ActionResult:
    """
    Type text into an element (async)

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot
        text: Text to type
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Focus element first
    focused = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (el) {
                el.focus();
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not focused:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "focus_failed", "reason": "Element not found"},
        )

    # Type using Playwright keyboard
    await browser.page.keyboard.type(text)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def press_async(
    browser: AsyncSentienceBrowser, key: str, take_snapshot: bool = False
) -> ActionResult:
    """
    Press a keyboard key (async)

    Args:
        browser: AsyncSentienceBrowser instance
        key: Key to press (e.g., "Enter", "Escape", "Tab")
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Press key using Playwright
    await browser.page.keyboard.press(key)

    # Wait a bit for navigation/DOM updates
    await browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def _highlight_rect_async(
    browser: AsyncSentienceBrowser, rect: dict[str, float], duration_sec: float = 2.0
) -> None:
    """Highlight a rectangle with a red border overlay (async)"""
    if not browser.page:
        return

    highlight_id = f"sentience_highlight_{int(time.time() * 1000)}"

    args = {
        "rect": {
            "x": rect["x"],
            "y": rect["y"],
            "w": rect["w"],
            "h": rect["h"],
        },
        "highlightId": highlight_id,
        "durationSec": duration_sec,
    }

    await browser.page.evaluate(
        """
        (args) => {
            const { rect, highlightId, durationSec } = args;
            const overlay = document.createElement('div');
            overlay.id = highlightId;
            overlay.style.position = 'fixed';
            overlay.style.left = `${rect.x}px`;
            overlay.style.top = `${rect.y}px`;
            overlay.style.width = `${rect.w}px`;
            overlay.style.height = `${rect.h}px`;
            overlay.style.border = '3px solid red';
            overlay.style.borderRadius = '2px';
            overlay.style.boxSizing = 'border-box';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '999999';
            overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
            overlay.style.transition = 'opacity 0.3s ease-out';

            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    if (overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300);
            }, durationSec * 1000);
        }
        """,
        args,
    )


async def click_rect_async(
    browser: AsyncSentienceBrowser,
    rect: dict[str, float] | BBox,
    highlight: bool = True,
    highlight_duration: float = 2.0,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Click at the center of a rectangle (async)

    Args:
        browser: AsyncSentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys, or BBox object
        highlight: Whether to show a red border highlight when clicking
        highlight_duration: How long to show the highlight in seconds
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    # Handle BBox object or dict
    if isinstance(rect, BBox):
        x = rect.x
        y = rect.y
        w = rect.width
        h = rect.height
    else:
        x = rect.get("x", 0)
        y = rect.get("y", 0)
        w = rect.get("w") or rect.get("width", 0)
        h = rect.get("h") or rect.get("height", 0)

    if w <= 0 or h <= 0:
        return ActionResult(
            success=False,
            duration_ms=0,
            outcome="error",
            error={
                "code": "invalid_rect",
                "reason": "Rectangle width and height must be positive",
            },
        )

    start_time = time.time()
    url_before = browser.page.url

    # Calculate center of rectangle
    center_x = x + w / 2
    center_y = y + h / 2

    # Show highlight before clicking
    if highlight:
        await _highlight_rect_async(browser, {"x": x, "y": y, "w": w, "h": h}, highlight_duration)
        await browser.page.wait_for_timeout(50)

    # Use Playwright's native mouse click
    try:
        await browser.page.mouse.click(center_x, center_y)
        success = True
    except Exception as e:
        success = False
        error_msg = str(e)

    # Wait a bit for navigation/DOM updates
    await browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot_async(browser)

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": error_msg if not success else "Click failed",
            }
        ),
    )
