"""
Browser-use adapter for Sentience SDK.

This module provides BrowserUseAdapter which wraps browser-use's BrowserSession
and provides a CDPBackendV0 for Sentience operations.

Usage:
    from browser_use import BrowserSession, BrowserProfile
    from predicate import get_extension_dir
    from predicate.backends import BrowserUseAdapter

    # Create browser-use session with Sentience extension
    profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
    session = BrowserSession(browser_profile=profile)
    await session.start()

    # Create Sentience adapter
    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Use backend for Sentience operations
    viewport = await backend.refresh_page_info()
    await backend.mouse_click(100, 200)
"""

from typing import TYPE_CHECKING, Any

from .cdp_backend import CDPBackendV0, CDPTransport

if TYPE_CHECKING:
    # Import browser-use types only for type checking
    # This avoids requiring browser-use as a hard dependency
    pass


class BrowserUseCDPTransport(CDPTransport):
    """
    CDP transport implementation for browser-use.

    Wraps browser-use's CDP client to provide the CDPTransport interface.
    Uses cdp-use library pattern: cdp_client.send.Domain.method(params={}, session_id=)
    """

    def __init__(self, cdp_client: Any, session_id: str) -> None:
        """
        Initialize transport with browser-use CDP client.

        Args:
            cdp_client: browser-use's CDP client (from cdp_session.cdp_client)
            session_id: CDP session ID (from cdp_session.session_id)
        """
        self._client = cdp_client
        self._session_id = session_id

    async def send(self, method: str, params: dict | None = None) -> dict:
        """
        Send CDP command using browser-use's cdp-use client.

        Translates method name like "Runtime.evaluate" to
        cdp_client.send.Runtime.evaluate(params={...}, session_id=...).

        Args:
            method: CDP method name, e.g., "Runtime.evaluate"
            params: Method parameters

        Returns:
            CDP response dict
        """
        # Split method into domain and method name
        # e.g., "Runtime.evaluate" -> ("Runtime", "evaluate")
        parts = method.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid CDP method format: {method}")

        domain_name, method_name = parts

        # Get the domain object from cdp_client.send
        domain = getattr(self._client.send, domain_name, None)
        if domain is None:
            raise ValueError(f"Unknown CDP domain: {domain_name}")

        # Get the method from the domain
        method_func = getattr(domain, method_name, None)
        if method_func is None:
            raise ValueError(f"Unknown CDP method: {method}")

        # Call the method with params and session_id
        result = await method_func(
            params=params or {},
            session_id=self._session_id,
        )

        # cdp-use returns the result directly or None
        return result if result is not None else {}


class BrowserUseAdapter:
    """
    Adapter to use Sentience with browser-use's BrowserSession.

    This adapter:
    1. Wraps browser-use's CDP client with BrowserUseCDPTransport
    2. Creates CDPBackendV0 for Sentience operations
    3. Provides access to the underlying page for extension calls

    Example:
        from browser_use import BrowserSession, BrowserProfile
        from predicate import get_extension_dir, snapshot_async, SnapshotOptions
        from predicate.backends import BrowserUseAdapter

        # Setup browser-use with Sentience extension
        profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
        session = BrowserSession(browser_profile=profile)
        await session.start()

        # Create adapter and backend
        adapter = BrowserUseAdapter(session)
        backend = await adapter.create_backend()

        # Navigate (using browser-use)
        page = await session.get_current_page()
        await page.goto("https://example.com")

        # Take Sentience snapshot (uses extension)
        snap = await snapshot_async(adapter, SnapshotOptions())

        # Use backend for precise clicking
        await backend.mouse_click(snap.elements[0].bbox.x, snap.elements[0].bbox.y)
    """

    def __init__(self, session: Any) -> None:
        """
        Initialize adapter with browser-use BrowserSession.

        Args:
            session: browser-use BrowserSession instance
        """
        self._session = session
        self._backend: CDPBackendV0 | None = None
        self._transport: BrowserUseCDPTransport | None = None

    @property
    def page(self) -> Any:
        """
        Get the current Playwright page from browser-use.

        This is needed for Sentience snapshot() which calls window.sentience.snapshot().

        Returns:
            Playwright Page object
        """
        # browser-use stores page in session
        # Access pattern may vary by browser-use version
        if hasattr(self._session, "page"):
            return self._session.page
        if hasattr(self._session, "_page"):
            return self._session._page
        if hasattr(self._session, "get_current_page"):
            # This is async, but we need sync access for property
            # Caller should use get_page_async() instead
            raise RuntimeError("Use await adapter.get_page_async() to get the page")
        raise RuntimeError("Could not find page in browser-use session")

    async def get_page_async(self) -> Any:
        """
        Get the current Playwright page (async).

        Returns:
            Playwright Page object
        """
        if hasattr(self._session, "get_current_page"):
            return await self._session.get_current_page()
        return self.page

    @property
    def api_key(self) -> str | None:
        """
        API key for Sentience API (for snapshot compatibility).

        Returns None since browser-use users pass api_key via SnapshotOptions.
        """
        return None

    @property
    def api_url(self) -> str | None:
        """
        API URL for Sentience API (for snapshot compatibility).

        Returns None to use default.
        """
        return None

    async def create_backend(self) -> CDPBackendV0:
        """
        Create CDP backend for Sentience operations.

        This method:
        1. Gets or creates a CDP session from browser-use
        2. Creates BrowserUseCDPTransport to wrap the CDP client
        3. Creates CDPBackendV0 with the transport

        Returns:
            CDPBackendV0 instance ready for use

        Raises:
            RuntimeError: If CDP session cannot be created
        """
        if self._backend is not None:
            return self._backend

        # Get CDP session from browser-use
        # browser-use uses: cdp_session = await session.get_or_create_cdp_session()
        if not hasattr(self._session, "get_or_create_cdp_session"):
            raise RuntimeError(
                "browser-use session does not have get_or_create_cdp_session method. "
                "Make sure you're using a compatible version of browser-use."
            )

        cdp_session = await self._session.get_or_create_cdp_session()

        # Extract CDP client and session ID
        cdp_client = cdp_session.cdp_client
        session_id = cdp_session.session_id

        # Create transport and backend
        self._transport = BrowserUseCDPTransport(cdp_client, session_id)
        self._backend = CDPBackendV0(self._transport)

        return self._backend

    async def get_transport(self) -> BrowserUseCDPTransport:
        """
        Get the CDP transport (creates backend if needed).

        Returns:
            BrowserUseCDPTransport instance
        """
        if self._transport is None:
            await self.create_backend()
        assert self._transport is not None
        return self._transport
