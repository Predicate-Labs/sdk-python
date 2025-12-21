"""
Actions v1 - click, type, press
"""

import time
from typing import Optional
from .browser import SentienceBrowser
from .models import ActionResult, Snapshot
from .snapshot import snapshot


def click(browser: SentienceBrowser, element_id: int, take_snapshot: bool = False) -> ActionResult:
    """
    Click an element by ID
    
    Args:
        browser: SentienceBrowser instance
        element_id: Element ID from snapshot
        take_snapshot: Whether to take snapshot after action (optional in Week 1)
    
    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    
    start_time = time.time()
    url_before = browser.page.url
    
    # Call extension click method
    success = browser.page.evaluate(
        """
        (id) => {
            return window.sentience.click(id);
        }
        """,
        element_id,
    )
    
    # Wait a bit for navigation/DOM updates
    browser.page.wait_for_timeout(500)
    
    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after
    
    # Determine outcome
    outcome: Optional[str] = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"
    
    # Optional snapshot after
    snapshot_after: Optional[Snapshot] = None
    if take_snapshot:
        snapshot_after = snapshot(browser)
    
    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=None if success else {"code": "click_failed", "reason": "Element not found or not clickable"},
    )


def type_text(browser: SentienceBrowser, element_id: int, text: str, take_snapshot: bool = False) -> ActionResult:
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
    
    snapshot_after: Optional[Snapshot] = None
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
    
    snapshot_after: Optional[Snapshot] = None
    if take_snapshot:
        snapshot_after = snapshot(browser)
    
    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )

