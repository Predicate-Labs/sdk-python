"""
Enums for Sentience API methods and agent actions.

This module provides type-safe enums for:
1. window.sentience API methods (extension-level)
2. Agent action types (high-level automation commands)
"""

from enum import Enum


class SentienceMethod(str, Enum):
    """
    Enum for window.sentience API methods.

    These are the actual methods available on the window.sentience object
    injected by the Chrome extension.
    """

    # Core snapshot and element discovery
    SNAPSHOT = "snapshot"
    """Take a snapshot of the current page with element geometry and metadata."""

    # Element interaction
    CLICK = "click"
    """Click an element by its ID from the snapshot registry."""

    # Content extraction
    READ = "read"
    """Read page content as raw HTML, text, or markdown."""

    FIND_TEXT_RECT = "findTextRect"
    """Find exact pixel coordinates of text occurrences on the page."""

    # Visual overlay
    SHOW_OVERLAY = "showOverlay"
    """Show visual overlay highlighting elements with importance scores."""

    CLEAR_OVERLAY = "clearOverlay"
    """Clear the visual overlay."""

    # Developer tools
    START_RECORDING = "startRecording"
    """Start recording mode for golden set collection (developer tool)."""

    def __str__(self) -> str:
        """Return the method name as a string."""
        return self.value


class AgentAction(str, Enum):
    """
    Enum for high-level agent action types.

    These are the action commands that agents can execute. They may use
    one or more window.sentience methods or Playwright APIs directly.
    """

    # Element interaction
    CLICK = "click"
    """Click an element by ID. Uses window.sentience.click() or Playwright mouse.click()."""

    TYPE = "type"
    """Type text into an input element. Uses Playwright keyboard.type() directly."""

    PRESS = "press"
    """Press a keyboard key (Enter, Escape, Tab, etc.). Uses Playwright keyboard.press()."""

    # Navigation
    NAVIGATE = "navigate"
    """Navigate to a URL. Uses Playwright page.goto() directly."""

    SCROLL = "scroll"
    """Scroll the page or an element. Uses Playwright page.mouse.wheel() or element.scrollIntoView()."""

    # Completion
    FINISH = "finish"
    """Signal that the agent task is complete. No browser action, just status update."""

    # Wait/verification
    WAIT = "wait"
    """Wait for a condition or duration. Uses Playwright wait_for_* methods."""

    def __str__(self) -> str:
        """Return the action name as a string."""
        return self.value
