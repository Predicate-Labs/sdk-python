"""
Backend-agnostic snapshot for browser-use integration.

Takes Sentience snapshots using BrowserBackendV0 protocol,
enabling element grounding with browser-use or other frameworks.

Usage with browser-use:
    from sentience.backends import BrowserUseAdapter, snapshot, CachedSnapshot

    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Take snapshot
    snap = await snapshot(backend)
    print(f"Found {len(snap.elements)} elements")

    # With caching (reuse if fresh)
    cache = CachedSnapshot(backend, max_age_ms=2000)
    snap1 = await cache.get()  # Fresh snapshot
    snap2 = await cache.get()  # Returns cached if < 2s old
    cache.invalidate()  # Force refresh on next get()
"""

import time
from typing import TYPE_CHECKING, Any

from ..models import Snapshot, SnapshotOptions

if TYPE_CHECKING:
    from .protocol_v0 import BrowserBackendV0


class CachedSnapshot:
    """
    Snapshot cache with staleness detection.

    Caches snapshots and returns cached version if still fresh.
    Useful for reducing redundant snapshot calls in action loops.

    Usage:
        cache = CachedSnapshot(backend, max_age_ms=2000)

        # First call takes fresh snapshot
        snap1 = await cache.get()

        # Second call returns cached if < 2s old
        snap2 = await cache.get()

        # Invalidate after actions that change DOM
        await click(backend, element.bbox)
        cache.invalidate()

        # Next get() will take fresh snapshot
        snap3 = await cache.get()
    """

    def __init__(
        self,
        backend: "BrowserBackendV0",
        max_age_ms: int = 2000,
        options: SnapshotOptions | None = None,
    ) -> None:
        """
        Initialize cached snapshot.

        Args:
            backend: BrowserBackendV0 implementation
            max_age_ms: Maximum cache age in milliseconds (default: 2000)
            options: Default snapshot options
        """
        self._backend = backend
        self._max_age_ms = max_age_ms
        self._options = options
        self._cached: Snapshot | None = None
        self._cached_at: float = 0  # timestamp in seconds
        self._cached_url: str | None = None

    async def get(
        self,
        options: SnapshotOptions | None = None,
        force_refresh: bool = False,
    ) -> Snapshot:
        """
        Get snapshot, using cache if fresh.

        Args:
            options: Override default options for this call
            force_refresh: If True, always take fresh snapshot

        Returns:
            Snapshot (cached or fresh)
        """
        # Check if we need to refresh
        if force_refresh or self._is_stale():
            self._cached = await snapshot(
                self._backend,
                options or self._options,
            )
            self._cached_at = time.time()
            self._cached_url = self._cached.url

        assert self._cached is not None
        return self._cached

    def invalidate(self) -> None:
        """
        Invalidate cache, forcing refresh on next get().

        Call this after actions that modify the DOM.
        """
        self._cached = None
        self._cached_at = 0
        self._cached_url = None

    def _is_stale(self) -> bool:
        """Check if cache is stale and needs refresh."""
        if self._cached is None:
            return True

        # Check age
        age_ms = (time.time() - self._cached_at) * 1000
        if age_ms > self._max_age_ms:
            return True

        return False

    @property
    def is_cached(self) -> bool:
        """Check if a cached snapshot exists."""
        return self._cached is not None

    @property
    def age_ms(self) -> float:
        """Get age of cached snapshot in milliseconds."""
        if self._cached is None:
            return float("inf")
        return (time.time() - self._cached_at) * 1000


async def snapshot(
    backend: "BrowserBackendV0",
    options: SnapshotOptions | None = None,
) -> Snapshot:
    """
    Take a Sentience snapshot using the backend protocol.

    This function calls window.sentience.snapshot() via the backend's eval(),
    enabling snapshot collection with any BrowserBackendV0 implementation.

    Requires:
        - Sentience extension loaded in browser (via --load-extension)
        - Extension injected window.sentience API

    Args:
        backend: BrowserBackendV0 implementation (CDPBackendV0, PlaywrightBackend, etc.)
        options: Snapshot options (limit, filter, screenshot, etc.)

    Returns:
        Snapshot with elements, viewport, and optional screenshot

    Example:
        from sentience.backends import BrowserUseAdapter
        from sentience.backends.snapshot import snapshot_from_backend

        adapter = BrowserUseAdapter(session)
        backend = await adapter.create_backend()

        # Basic snapshot
        snap = await snapshot_from_backend(backend)

        # With options
        snap = await snapshot_from_backend(backend, SnapshotOptions(
            limit=100,
            screenshot=True
        ))
    """
    if options is None:
        options = SnapshotOptions()

    # Wait for extension injection
    await _wait_for_extension(backend, timeout_ms=5000)

    # Build options dict for extension API
    ext_options = _build_extension_options(options)

    # Call extension's snapshot function
    result = await backend.eval(f"""
        (() => {{
            const options = {_json_serialize(ext_options)};
            return window.sentience.snapshot(options);
        }})()
    """)

    if result is None:
        raise RuntimeError(
            "window.sentience.snapshot() returned null. "
            "Is the Sentience extension loaded and injected?"
        )

    # Show overlay if requested
    if options.show_overlay:
        raw_elements = result.get("raw_elements", [])
        if raw_elements:
            await backend.eval(f"""
                (() => {{
                    if (window.sentience && window.sentience.showOverlay) {{
                        window.sentience.showOverlay({_json_serialize(raw_elements)}, null);
                    }}
                }})()
            """)

    # Build and return Snapshot
    return Snapshot(**result)


async def _wait_for_extension(
    backend: "BrowserBackendV0",
    timeout_ms: int = 5000,
) -> None:
    """
    Wait for Sentience extension to inject window.sentience API.

    Args:
        backend: BrowserBackendV0 implementation
        timeout_ms: Maximum wait time

    Raises:
        RuntimeError: If extension not injected within timeout
    """
    import asyncio

    start = time.monotonic()
    timeout_sec = timeout_ms / 1000.0

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout_sec:
            # Gather diagnostics
            try:
                diag = await backend.eval("""
                    (() => ({
                        sentience_defined: typeof window.sentience !== 'undefined',
                        sentience_snapshot: typeof window.sentience?.snapshot === 'function',
                        url: window.location.href
                    }))()
                """)
            except Exception:
                diag = {"error": "Could not gather diagnostics"}

            raise RuntimeError(
                f"Sentience extension failed to inject window.sentience API "
                f"within {timeout_ms}ms. Diagnostics: {diag}"
            )

        # Check if extension is ready
        try:
            ready = await backend.eval(
                "typeof window.sentience !== 'undefined' && "
                "typeof window.sentience.snapshot === 'function'"
            )
            if ready:
                return
        except Exception:
            pass  # Keep polling

        await asyncio.sleep(0.1)


def _build_extension_options(options: SnapshotOptions) -> dict[str, Any]:
    """Build options dict for extension API call."""
    ext_options: dict[str, Any] = {}

    # Screenshot config
    if options.screenshot is not False:
        if hasattr(options.screenshot, "model_dump"):
            ext_options["screenshot"] = options.screenshot.model_dump()
        else:
            ext_options["screenshot"] = options.screenshot

    # Limit (only if not default)
    if options.limit != 50:
        ext_options["limit"] = options.limit

    # Filter
    if options.filter is not None:
        if hasattr(options.filter, "model_dump"):
            ext_options["filter"] = options.filter.model_dump()
        else:
            ext_options["filter"] = options.filter

    return ext_options


def _json_serialize(obj: Any) -> str:
    """Serialize object to JSON string for embedding in JS."""
    import json
    return json.dumps(obj)
