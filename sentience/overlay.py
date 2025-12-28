"""
Visual overlay utilities - show/clear element highlights in browser
"""

from typing import Any

from .browser import SentienceBrowser
from .models import Element, Snapshot


def show_overlay(
    browser: SentienceBrowser,
    elements: list[Element] | list[dict[str, Any]] | Snapshot,
    target_element_id: int | None = None,
) -> None:
    """
    Display visual overlay highlighting elements in the browser

    This function shows a Shadow DOM overlay with color-coded borders around
    detected elements. Useful for debugging, learning, and validating element detection.

    Args:
        browser: SentienceBrowser instance
        elements: Can be:
            - List of Element objects (from snapshot.elements)
            - List of raw element dicts (from snapshot result or API response)
            - Snapshot object (will use snapshot.elements)
        target_element_id: Optional ID of element to highlight in red (default: None)

    Color Coding:
        - Red: Target element (when target_element_id is specified)
        - Blue: Primary elements (is_primary=true)
        - Green: Regular interactive elements

    Visual Indicators:
        - Border thickness and opacity scale with importance score
        - Semi-transparent fill for better visibility
        - Importance badges showing scores
        - Star icon for primary elements
        - Target emoji for the target element

    Auto-clear: Overlay automatically disappears after 5 seconds

    Example:
        # Show overlay from snapshot
        snap = snapshot(browser)
        show_overlay(browser, snap)

        # Show overlay with custom elements
        elements = [{"id": 1, "bbox": {"x": 100, "y": 100, "width": 200, "height": 50}, ...}]
        show_overlay(browser, elements)

        # Show overlay with target element highlighted in red
        show_overlay(browser, snap, target_element_id=42)

        # Clear overlay manually before 5 seconds
        clear_overlay(browser)
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    # Handle different input types
    if isinstance(elements, Snapshot):
        # Extract elements from Snapshot object
        elements_list = [el.model_dump() for el in elements.elements]
    elif isinstance(elements, list) and len(elements) > 0:
        # Check if it's a list of Element objects or dicts
        if hasattr(elements[0], "model_dump"):
            # List of Element objects
            elements_list = [el.model_dump() for el in elements]
        else:
            # Already a list of dicts
            elements_list = elements
    else:
        raise ValueError("elements must be a Snapshot, list of Element objects, or list of dicts")

    # Call extension API
    browser.page.evaluate(
        """
        (args) => {
            if (window.sentience && window.sentience.showOverlay) {
                window.sentience.showOverlay(args.elements, args.targetId);
            } else {
                console.warn('[Sentience SDK] showOverlay not available - is extension loaded?');
            }
        }
        """,
        {"elements": elements_list, "targetId": target_element_id},
    )


def clear_overlay(browser: SentienceBrowser) -> None:
    """
    Clear the visual overlay manually (before 5-second auto-clear)

    Args:
        browser: SentienceBrowser instance

    Example:
        show_overlay(browser, snap)
        # ... inspect overlay ...
        clear_overlay(browser)  # Remove immediately
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    browser.page.evaluate(
        """
        () => {
            if (window.sentience && window.sentience.clearOverlay) {
                window.sentience.clearOverlay();
            }
        }
        """
    )
