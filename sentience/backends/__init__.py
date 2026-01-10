"""
Browser backend abstractions for Sentience SDK.

This module provides backend protocols and implementations that allow
Sentience actions (click, type, scroll) to work with different browser
automation frameworks.

Supported Backends
------------------

**PlaywrightBackend**
    Wraps Playwright Page objects. Use this when integrating with existing
    SentienceBrowser or Playwright-based code.

**CDPBackendV0**
    Low-level CDP (Chrome DevTools Protocol) backend. Use this when you have
    direct access to a CDP client and session.

**BrowserUseAdapter**
    High-level adapter for browser-use framework. Automatically creates a
    CDPBackendV0 from a BrowserSession.

Quick Start with browser-use
----------------------------

.. code-block:: python

    from browser_use import BrowserSession, BrowserProfile
    from sentience import get_extension_dir, find
    from sentience.backends import BrowserUseAdapter, snapshot, click, type_text

    # Setup browser-use with Sentience extension
    profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
    session = BrowserSession(browser_profile=profile)
    await session.start()

    # Create adapter and backend
    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Take snapshot and interact with elements
    snap = await snapshot(backend)
    search_box = find(snap, 'role=textbox[name*="Search"]')
    await click(backend, search_box.bbox)
    await type_text(backend, "Sentience AI")

Snapshot Caching
----------------

Use CachedSnapshot to reduce redundant snapshot calls in action loops:

.. code-block:: python

    from sentience.backends import CachedSnapshot

    cache = CachedSnapshot(backend, max_age_ms=2000)

    snap1 = await cache.get()  # Takes fresh snapshot
    snap2 = await cache.get()  # Returns cached if < 2s old

    await click(backend, element.bbox)
    cache.invalidate()  # Force refresh on next get()

Error Handling
--------------

The module provides specific exceptions for common failure modes:

- ``ExtensionNotLoadedError``: Extension not loaded in browser launch args
- ``SnapshotError``: window.sentience.snapshot() failed
- ``ActionError``: Click/type/scroll operation failed

All exceptions inherit from ``SentienceBackendError`` and include helpful
fix suggestions in their error messages.

.. code-block:: python

    from sentience.backends import ExtensionNotLoadedError, snapshot

    try:
        snap = await snapshot(backend)
    except ExtensionNotLoadedError as e:
        print(f"Fix suggestion: {e}")
"""

from .actions import click, scroll, scroll_to_element, type_text, wait_for_stable
from .browser_use_adapter import BrowserUseAdapter, BrowserUseCDPTransport
from .cdp_backend import CDPBackendV0, CDPTransport
from .exceptions import (
    ActionError,
    BackendEvalError,
    ExtensionDiagnostics,
    ExtensionInjectionError,
    ExtensionNotLoadedError,
    SentienceBackendError,
    SnapshotError,
)
from .playwright_backend import PlaywrightBackend
from .protocol_v0 import BrowserBackendV0, LayoutMetrics, ViewportInfo
from .sentience_context import SentienceContext, SentienceContextState
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
    # SentienceContext (Token-Slasher Context Middleware)
    "SentienceContext",
    "SentienceContextState",
    # Backend-agnostic functions
    "snapshot",
    "CachedSnapshot",
    "click",
    "type_text",
    "scroll",
    "scroll_to_element",
    "wait_for_stable",
    # Exceptions
    "SentienceBackendError",
    "ExtensionNotLoadedError",
    "ExtensionInjectionError",
    "ExtensionDiagnostics",
    "BackendEvalError",
    "SnapshotError",
    "ActionError",
]
