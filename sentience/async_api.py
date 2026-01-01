"""
Async API for Sentience SDK - Convenience re-exports

This module re-exports all async functions for backward compatibility and developer convenience.
You can also import directly from their respective modules:

    # Option 1: From async_api (recommended for convenience)
    from sentience.async_api import (
        AsyncSentienceBrowser,
        snapshot_async,
        click_async,
        wait_for_async,
        screenshot_async,
        find_text_rect_async,
        # ... all async functions in one place
    )

    # Option 2: From respective modules (also works)
    from sentience.browser import AsyncSentienceBrowser
    from sentience.snapshot import snapshot_async
    from sentience.actions import click_async
"""

# ========== Browser ==========
# Re-export AsyncSentienceBrowser from browser.py (moved there for better organization)
from sentience.browser import AsyncSentienceBrowser

# ========== Snapshot (Phase 1) ==========
# Re-export async snapshot functions from snapshot.py
from sentience.snapshot import snapshot_async

# ========== Actions (Phase 1) ==========
# Re-export async action functions from actions.py
from sentience.actions import (
    click_async,
    type_text_async,
    press_async,
    click_rect_async,
)

# ========== Phase 2A: Core Utilities ==========
# Re-export async wait function from wait.py
from sentience.wait import wait_for_async

# Re-export async screenshot function from screenshot.py
from sentience.screenshot import screenshot_async

# Re-export async text search function from text_search.py
from sentience.text_search import find_text_rect_async

# ========== Phase 2B: Supporting Utilities (Future) ==========
# TODO: Re-export when implemented
# from sentience.read import read_async
# from sentience.overlay import show_overlay_async, clear_overlay_async
# from sentience.expect import expect_async, ExpectationAsync

# ========== Phase 2C: Agent Layer (Future) ==========
# TODO: Re-export when implemented
# from sentience.agent import SentienceAgentAsync
# from sentience.base_agent import BaseAgentAsync

# ========== Phase 2D: Developer Tools (Future) ==========
# TODO: Re-export when implemented
# from sentience.recorder import RecorderAsync
# from sentience.inspector import InspectorAsync

# ========== Query Functions (Pure Functions - No Async Needed) ==========
# Re-export query functions (pure functions, no async needed)
from sentience.query import find, query

__all__ = [
    # Browser
    "AsyncSentienceBrowser",  # Re-exported from browser.py
    # Snapshot (Phase 1)
    "snapshot_async",  # Re-exported from snapshot.py
    # Actions (Phase 1)
    "click_async",  # Re-exported from actions.py
    "type_text_async",  # Re-exported from actions.py
    "press_async",  # Re-exported from actions.py
    "click_rect_async",  # Re-exported from actions.py
    # Phase 2A: Core Utilities
    "wait_for_async",  # Re-exported from wait.py
    "screenshot_async",  # Re-exported from screenshot.py
    "find_text_rect_async",  # Re-exported from text_search.py
    # Phase 2B: Supporting Utilities (Future - uncomment when implemented)
    # "read_async",
    # "show_overlay_async",
    # "clear_overlay_async",
    # "expect_async",
    # "ExpectationAsync",
    # Phase 2C: Agent Layer (Future - uncomment when implemented)
    # "SentienceAgentAsync",
    # "BaseAgentAsync",
    # Phase 2D: Developer Tools (Future - uncomment when implemented)
    # "RecorderAsync",
    # "InspectorAsync",
    # Query Functions
    "find",  # Re-exported from query.py
    "query",  # Re-exported from query.py
]
