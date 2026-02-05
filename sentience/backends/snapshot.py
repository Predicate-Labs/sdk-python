"""
Backend-agnostic snapshot for browser-use integration.

Takes Sentience snapshots using BrowserBackend protocol,
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

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ..constants import SENTIENCE_API_URL
from ..models import Element, Snapshot, SnapshotOptions
from ..snapshot import (
    _build_snapshot_payload,
    _merge_api_result_with_local,
    _post_snapshot_to_gateway_async,
)
from .exceptions import ExtensionDiagnostics, ExtensionNotLoadedError, SnapshotError

if TYPE_CHECKING:
    from .protocol import BrowserBackend


def _is_execution_context_destroyed_error(e: Exception) -> bool:
    """
    Playwright (and other browser backends) can throw while a navigation is in-flight.

    Common symptoms:
    - "Execution context was destroyed, most likely because of a navigation"
    - "Cannot find context with specified id"
    """
    msg = str(e).lower()
    return (
        "execution context was destroyed" in msg
        or "most likely because of a navigation" in msg
        or "cannot find context with specified id" in msg
    )


async def _eval_with_navigation_retry(
    backend: "BrowserBackend",
    expression: str,
    *,
    retries: int = 10,
    settle_state: str = "interactive",
    settle_timeout_ms: int = 10000,
) -> Any:
    """
    Evaluate JS, retrying once/ twice if the page is mid-navigation.

    This makes snapshots resilient to cases like:
    - press Enter (navigation) → snapshot immediately → context destroyed
    """
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await backend.eval(expression)
        except Exception as e:
            last_err = e
            if not _is_execution_context_destroyed_error(e) or attempt >= retries:
                raise
            # Navigation is in-flight; wait for new document context then retry.
            try:
                await backend.wait_ready_state(state=settle_state, timeout_ms=settle_timeout_ms)  # type: ignore[arg-type]
            except Exception:
                # If readyState polling also fails mid-nav, still retry after a short backoff.
                pass
            # Exponential-ish backoff (caps quickly), tuned for real navigations.
            await asyncio.sleep(min(0.25 * (attempt + 1), 1.5))

    # Unreachable in practice, but keeps type-checkers happy.
    raise last_err if last_err else RuntimeError("eval failed")


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
        backend: "BrowserBackend",
        max_age_ms: int = 2000,
        options: SnapshotOptions | None = None,
    ) -> None:
        """
        Initialize cached snapshot.

        Args:
            backend: BrowserBackend implementation
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
    backend: "BrowserBackend",
    options: SnapshotOptions | None = None,
) -> Snapshot:
    """
    Take a Sentience snapshot using the backend protocol.

    This function respects the `use_api` option and can call either:
    - Server-side API (Pro/Enterprise tier) when `use_api=True` and API key is provided
    - Local extension (Free tier) when `use_api=False` or no API key

    Requires:
        - Sentience extension loaded in browser (via --load-extension)
        - Extension injected window.sentience API

    Args:
        backend: BrowserBackend implementation (CDPBackendV0, PlaywrightBackend, etc.)
        options: Snapshot options (limit, filter, screenshot, use_api, sentience_api_key, etc.)

    Returns:
        Snapshot with elements, viewport, and optional screenshot

    Example:
        from sentience.backends import BrowserUseAdapter
        from sentience.backends.snapshot import snapshot
        from sentience.models import SnapshotOptions

        adapter = BrowserUseAdapter(session)
        backend = await adapter.create_backend()

        # Basic snapshot (uses local extension)
        snap = await snapshot(backend)

        # With server-side API (Pro/Enterprise tier)
        snap = await snapshot(backend, SnapshotOptions(
            use_api=True,
            sentience_api_key="sk_pro_xxxxx",
            limit=100,
            screenshot=True
        ))

        # Force local extension (Free tier)
        snap = await snapshot(backend, SnapshotOptions(
            use_api=False
        ))
    """
    if options is None:
        options = SnapshotOptions()

    # Determine if we should use server-side API
    # Same logic as main snapshot() function in sentience/snapshot.py
    should_use_api = (
        options.use_api if options.use_api is not None else (options.sentience_api_key is not None)
    )

    if should_use_api and options.sentience_api_key:
        # Use server-side API (Pro/Enterprise tier)
        return await _snapshot_via_api(backend, options)
    else:
        # Use local extension (Free tier)
        return await _snapshot_via_extension(backend, options)


def _normalize_ws(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _dedupe_key(el: Element) -> tuple:
    """
    Best-effort stable dedupe key across scroll-sampled snapshots.

    Notes:
    - IDs are not reliable across snapshots (virtualization can remount nodes).
    - BBox coordinates are viewport-relative and depend on scroll position.
    - Prefer href/name/text + approximate document position when available.
    """
    href = (el.href or "").strip()
    if href:
        return ("href", href)

    name = _normalize_ws(el.name or "")
    if name:
        return ("role_name", el.role, name)

    text = _normalize_ws(el.text or "")
    doc_y = el.doc_y
    if text:
        # Use doc_y when present (more stable across scroll positions than bbox.y).
        if isinstance(doc_y, (int, float)):
            return ("role_text_docy", el.role, text[:120], int(float(doc_y) // 10))
        return ("role_text", el.role, text[:120])

    # Fallback: role + approximate position
    if isinstance(doc_y, (int, float)):
        return ("role_docy", el.role, int(float(doc_y) // 10))

    # Last resort (can still dedupe within a single snapshot)
    return ("id", int(el.id))


def merge_snapshots(
    snaps: list[Snapshot],
    *,
    union_limit: int | None = None,
) -> Snapshot:
    """
    Merge multiple snapshots into a single "union snapshot" for analysis/extraction.

    CRITICAL:
    - Element bboxes are viewport-relative to the scroll position at the time each snapshot
      was taken. Do NOT use merged elements for direct clicking unless you also scroll
      back to their position.
    """
    if not snaps:
        raise ValueError("merge_snapshots requires at least one snapshot")

    base = snaps[0]
    best_by_key: dict[tuple, Element] = {}
    first_seen_idx: dict[tuple, int] = {}

    # Keep the "best" representative per key:
    # - Prefer higher importance (usually means in-viewport at that sampling moment)
    # - Prefer having href/text/name (more useful for extraction)
    def _quality_score(e: Element) -> tuple:
        has_href = 1 if (e.href or "").strip() else 0
        has_text = 1 if _normalize_ws(e.text or "") else 0
        has_name = 1 if _normalize_ws(e.name or "") else 0
        has_docy = 1 if isinstance(e.doc_y, (int, float)) else 0
        return (e.importance, has_href, has_text, has_name, has_docy)

    idx = 0
    for snap in snaps:
        for el in list(getattr(snap, "elements", []) or []):
            k = _dedupe_key(el)
            if k not in first_seen_idx:
                first_seen_idx[k] = idx
            prev = best_by_key.get(k)
            if prev is None or _quality_score(el) > _quality_score(prev):
                best_by_key[k] = el
            idx += 1

    merged: list[Element] = list(best_by_key.values())

    # Deterministic ordering: prefer document order when doc_y is available,
    # then fall back to "first seen" (stable for a given sampling sequence).
    def _sort_key(e: Element) -> tuple:
        doc_y = e.doc_y
        if isinstance(doc_y, (int, float)):
            return (0, float(doc_y), -int(e.importance))
        return (1, float("inf"), first_seen_idx.get(_dedupe_key(e), 10**9))

    merged.sort(key=_sort_key)

    if union_limit is not None:
        try:
            lim = max(1, int(union_limit))
        except (TypeError, ValueError):
            lim = None
        if lim is not None:
            merged = merged[:lim]

    # Construct a new Snapshot object with merged elements.
    # Keep base url/viewport/diagnostics, and drop screenshot by default to avoid confusion.
    data = base.model_dump()
    data["elements"] = [e.model_dump() for e in merged]
    data["screenshot"] = None
    return Snapshot(**data)


async def sampled_snapshot(
    backend: "BrowserBackend",
    *,
    options: SnapshotOptions | None = None,
    samples: int = 4,
    scroll_delta_y: float | None = None,
    settle_ms: int = 250,
    union_limit: int | None = None,
    restore_scroll: bool = True,
) -> Snapshot:
    """
    Take multiple snapshots while scrolling downward and return a merged union snapshot.

    Designed for long / virtualized results pages where a single viewport snapshot
    cannot cover enough relevant items.
    """
    if options is None:
        options = SnapshotOptions()

    k = max(1, int(samples))
    if k <= 1:
        return await snapshot(backend, options=options)

    # Baseline scroll position
    try:
        info = await backend.refresh_page_info()
        base_scroll_y = float(getattr(info, "scroll_y", 0.0) or 0.0)
        vh = float(getattr(info, "height", 800) or 800)
    except Exception:  # pylint: disable=broad-exception-caught
        base_scroll_y = 0.0
        vh = 800.0

    # Choose a conservative scroll delta if not provided.
    delta = float(scroll_delta_y) if scroll_delta_y is not None else (vh * 0.9)
    if delta <= 0:
        delta = max(200.0, vh * 0.9)

    snaps: list[Snapshot] = []
    try:
        # Snapshot at current position.
        snaps.append(await snapshot(backend, options=options))

        for _i in range(1, k):
            try:
                # Scroll by wheel delta (plays nicer with sites that hook scroll events).
                await backend.wheel(delta_y=delta)
            except Exception:  # pylint: disable=broad-exception-caught
                # Fallback: direct scrollTo
                try:
                    cur = await backend.eval("window.scrollY")
                    await backend.call("(y) => window.scrollTo(0, y)", [float(cur) + delta])
                except Exception:  # pylint: disable=broad-exception-caught
                    break

            if settle_ms > 0:
                await asyncio.sleep(float(settle_ms) / 1000.0)

            snaps.append(await snapshot(backend, options=options))
    finally:
        if restore_scroll:
            try:
                await backend.call("(y) => window.scrollTo(0, y)", [float(base_scroll_y)])
                if settle_ms > 0:
                    await asyncio.sleep(min(0.2, float(settle_ms) / 1000.0))
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    return merge_snapshots(snaps, union_limit=union_limit)


async def _wait_for_extension(
    backend: "BrowserBackend",
    timeout_ms: int = 5000,
) -> None:
    """
    Wait for Sentience extension to inject window.sentience API.

    Args:
        backend: BrowserBackend implementation
        timeout_ms: Maximum wait time

    Raises:
        RuntimeError: If extension not injected within timeout
    """
    import logging

    logger = logging.getLogger("sentience.backends.snapshot")

    start = time.monotonic()
    timeout_sec = timeout_ms / 1000.0
    poll_count = 0

    logger.debug(f"Waiting for extension injection (timeout={timeout_ms}ms)...")

    while True:
        elapsed = time.monotonic() - start
        poll_count += 1

        if poll_count % 10 == 0:  # Log every 10 polls (~1 second)
            logger.debug(f"Extension poll #{poll_count}, elapsed={elapsed*1000:.0f}ms")

        if elapsed >= timeout_sec:
            # Gather diagnostics
            try:
                diag_dict = await backend.eval(
                    """
                    (() => ({
                        sentience_defined: typeof window.sentience !== 'undefined',
                        sentience_snapshot: typeof window.sentience?.snapshot === 'function',
                        url: window.location.href,
                        extension_id: document.documentElement.dataset.sentienceExtensionId || null,
                        has_content_script: !!document.documentElement.dataset.sentienceExtensionId
                    }))()
                """
                )
                diagnostics = ExtensionDiagnostics.from_dict(diag_dict)
                logger.debug(f"Extension diagnostics: {diag_dict}")
            except Exception as e:
                diagnostics = ExtensionDiagnostics(error=f"Could not gather diagnostics: {e}")

            raise ExtensionNotLoadedError.from_timeout(
                timeout_ms=timeout_ms,
                diagnostics=diagnostics,
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


async def _snapshot_via_extension(
    backend: "BrowserBackend",
    options: SnapshotOptions,
) -> Snapshot:
    """Take snapshot using local extension (Free tier)"""
    # Wait for extension injection
    await _wait_for_extension(backend, timeout_ms=5000)

    # Build options dict for extension API
    ext_options = _build_extension_options(options)

    # Call extension's snapshot function
    result = await _eval_with_navigation_retry(
        backend,
        f"""
        (() => {{
            const options = {_json_serialize(ext_options)};
            return window.sentience.snapshot(options);
        }})()
    """,
    )

    if result is None:
        # Try to get URL for better error message
        try:
            url = await backend.eval("window.location.href")
        except Exception:
            url = None
        raise SnapshotError.from_null_result(url=url)

    # Show overlay if requested
    if options.show_overlay:
        raw_elements = result.get("raw_elements", [])
        if raw_elements:
            await _eval_with_navigation_retry(
                backend,
                f"""
                (() => {{
                    if (window.sentience && window.sentience.showOverlay) {{
                        window.sentience.showOverlay({_json_serialize(raw_elements)}, null);
                    }}
                }})()
            """,
            )

    # Build and return Snapshot
    return Snapshot(**result)


async def _snapshot_via_api(
    backend: "BrowserBackend",
    options: SnapshotOptions,
) -> Snapshot:
    """Take snapshot using server-side API (Pro/Enterprise tier)"""
    # Default API URL (same as main snapshot function)
    api_url = SENTIENCE_API_URL

    # Wait for extension injection (needed even for API mode to collect raw data)
    await _wait_for_extension(backend, timeout_ms=5000)

    # Step 1: Get raw data from local extension (always happens locally)
    raw_options: dict[str, Any] = {}
    if options.screenshot is not False:
        if hasattr(options.screenshot, "model_dump"):
            raw_options["screenshot"] = options.screenshot.model_dump()
        else:
            raw_options["screenshot"] = options.screenshot

    # Call extension to get raw elements
    raw_result = await _eval_with_navigation_retry(
        backend,
        f"""
        (() => {{
            const options = {_json_serialize(raw_options)};
            return window.sentience.snapshot(options);
        }})()
    """,
    )

    if raw_result is None:
        try:
            url = await backend.eval("window.location.href")
        except Exception:
            url = None
        raise SnapshotError.from_null_result(url=url)

    # Step 2: Send to server for smart ranking/filtering
    payload = _build_snapshot_payload(raw_result, options)

    try:
        api_result = await _post_snapshot_to_gateway_async(
            payload,
            options.sentience_api_key,
            api_url,
            timeout_s=options.gateway_timeout_s,
        )

        # Merge API result with local data (screenshot, etc.)
        snapshot_data = _merge_api_result_with_local(api_result, raw_result)

        # Show visual overlay if requested (use API-ranked elements)
        if options.show_overlay:
            elements = api_result.get("elements", [])
            if elements:
                await _eval_with_navigation_retry(
                    backend,
                    f"""
                    (() => {{
                        if (window.sentience && window.sentience.showOverlay) {{
                            window.sentience.showOverlay({_json_serialize(elements)}, null);
                        }}
                    }})()
                """,
                )

        return Snapshot(**snapshot_data)
    except (RuntimeError, ValueError):
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        # Preserve structured gateway details when available.
        try:
            from ..snapshot import SnapshotGatewayError  # type: ignore

            if isinstance(e, SnapshotGatewayError):
                raise
        except Exception:
            pass

        # Fallback to local extension on API error
        # This matches the behavior of the main snapshot function
        raise RuntimeError(
            f"Server-side snapshot API failed: {e}. "
            "Try using use_api=False to use local extension instead."
        ) from e


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
