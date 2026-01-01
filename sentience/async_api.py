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

# ========== Actions (Phase 1) ==========
# Re-export async action functions from actions.py
from sentience.actions import click_async, click_rect_async, press_async, type_text_async

# ========== Phase 2C: Agent Layer ==========
# Re-export async agent classes from agent.py and base_agent.py
from sentience.agent import SentienceAgentAsync
from sentience.base_agent import BaseAgentAsync

# ========== Browser ==========
# Re-export AsyncSentienceBrowser from browser.py (moved there for better organization)
from sentience.browser import AsyncSentienceBrowser

# Re-export async expect functions from expect.py
from sentience.expect import ExpectationAsync, expect_async
from sentience.inspector import InspectorAsync, inspect_async

# Re-export async overlay functions from overlay.py
from sentience.overlay import clear_overlay_async, show_overlay_async

# ========== Query Functions (Pure Functions - No Async Needed) ==========
# Re-export query functions (pure functions, no async needed)
from sentience.query import find, query

# ========== Phase 2B: Supporting Utilities ==========
# Re-export async read function from read.py
from sentience.read import read_async

# ========== Phase 2D: Developer Tools ==========
# Re-export async recorder and inspector from their modules
from sentience.recorder import RecorderAsync, record_async

# Re-export async screenshot function from screenshot.py
from sentience.screenshot import screenshot_async

# ========== Snapshot (Phase 1) ==========
# Re-export async snapshot functions from snapshot.py
from sentience.snapshot import snapshot_async

# Re-export async text search function from text_search.py
from sentience.text_search import find_text_rect_async

# ========== Phase 2A: Core Utilities ==========
# Re-export async wait function from wait.py
from sentience.wait import wait_for_async

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
    # Phase 2B: Supporting Utilities
    "read_async",  # Re-exported from read.py
    "show_overlay_async",  # Re-exported from overlay.py
    "clear_overlay_async",  # Re-exported from overlay.py
    "expect_async",  # Re-exported from expect.py
    "ExpectationAsync",  # Re-exported from expect.py
    # Phase 2C: Agent Layer
    "SentienceAgentAsync",  # Re-exported from agent.py
    "BaseAgentAsync",  # Re-exported from base_agent.py
    # Phase 2D: Developer Tools
    "RecorderAsync",  # Re-exported from recorder.py
    "record_async",  # Re-exported from recorder.py
    "InspectorAsync",  # Re-exported from inspector.py
    "inspect_async",  # Re-exported from inspector.py
    # Query Functions
    "find",  # Re-exported from query.py
    "query",  # Re-exported from query.py
]
