"""
Browser backend abstractions for Sentience SDK.

This module provides backend protocols and implementations that allow
Sentience actions (click, type, scroll) to work with different browser
automation frameworks.

Supported backends:
- PlaywrightBackend: Default backend using Playwright (existing SentienceBrowser)
- CDPBackendV0: CDP-based backend for browser-use integration

For browser-use integration:
    from browser_use import BrowserSession, BrowserProfile
    from sentience import get_extension_dir
    from sentience.backends import BrowserUseAdapter, snapshot, click, type_text

    # Setup browser-use with Sentience extension
    profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
    session = BrowserSession(browser_profile=profile)
    await session.start()

    # Create adapter and backend
    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Take snapshot and interact
    snap = await snapshot(backend)
    element = find(snap, 'role=button[name="Submit"]')
    await click(backend, element.bbox)
"""

from .actions import click, scroll, scroll_to_element, type_text, wait_for_stable
from .browser_use_adapter import BrowserUseAdapter, BrowserUseCDPTransport
from .cdp_backend import CDPBackendV0, CDPTransport
from .playwright_backend import PlaywrightBackend
from .protocol_v0 import BrowserBackendV0, LayoutMetrics, ViewportInfo
from .snapshot import CachedSnapshot, snapshot

__all__ = [
    # Protocol
    "BrowserBackendV0",
    # Models
    "ViewportInfo",
    "LayoutMetrics",
    # CDP Backend
    "CDPTransport",
    "CDPBackendV0",
    # Playwright Backend
    "PlaywrightBackend",
    # browser-use adapter
    "BrowserUseAdapter",
    "BrowserUseCDPTransport",
    # Backend-agnostic functions
    "snapshot",
    "CachedSnapshot",
    "click",
    "type_text",
    "scroll",
    "scroll_to_element",
    "wait_for_stable",
]
