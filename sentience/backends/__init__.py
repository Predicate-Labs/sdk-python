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
    from sentience.backends import BrowserUseAdapter, CDPBackendV0

    # Setup browser-use with Sentience extension
    profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
    session = BrowserSession(browser_profile=profile)
    await session.start()

    # Create adapter and backend
    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Use backend for precise operations
    await backend.mouse_click(100, 200)
"""

from .browser_use_adapter import BrowserUseAdapter, BrowserUseCDPTransport
from .cdp_backend import CDPBackendV0, CDPTransport
from .protocol_v0 import BrowserBackendV0, LayoutMetrics, ViewportInfo

__all__ = [
    # Protocol
    "BrowserBackendV0",
    # Models
    "ViewportInfo",
    "LayoutMetrics",
    # CDP Backend
    "CDPTransport",
    "CDPBackendV0",
    # browser-use adapter
    "BrowserUseAdapter",
    "BrowserUseCDPTransport",
]
