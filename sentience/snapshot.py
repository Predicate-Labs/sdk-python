"""
Snapshot functionality - calls window.sentience.snapshot() or server-side API
"""

import asyncio
import json
import os
import time
from typing import Any, Optional

import requests

from .browser import AsyncSentienceBrowser, SentienceBrowser
from .browser_evaluator import BrowserEvaluator
from .constants import SENTIENCE_API_URL
from .models import Snapshot, SnapshotOptions
from .sentience_methods import SentienceMethod

# Maximum payload size for API requests (10MB server limit)
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024


class SnapshotGatewayError(RuntimeError):
    """
    Structured error for server-side (gateway) snapshot failures.

    Keeps HTTP status/URL/response details available to callers for better logging/debugging.
    Subclasses RuntimeError for backward compatibility.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        request_id: str | None = None,
        response_text: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.request_id = request_id
        self.response_text = response_text
        # Note: callers should use `raise ... from cause` to preserve chaining.
        _ = cause

    @staticmethod
    def _snip(s: str | None, n: int = 400) -> str | None:
        if not s:
            return None
        t = str(s).replace("\n", " ").replace("\r", " ").strip()
        return t[:n]

    @classmethod
    def from_httpx(cls, e: Exception) -> "SnapshotGatewayError":
        status_code = None
        url = None
        request_id = None
        body = None
        try:
            resp = getattr(e, "response", None)
            if resp is not None:
                status_code = getattr(resp, "status_code", None)
                try:
                    url = str(getattr(resp, "url", None) or "")
                except Exception:
                    url = None
                try:
                    headers = getattr(resp, "headers", None) or {}
                    request_id = headers.get("x-request-id") or headers.get("x-trace-id")
                except Exception:
                    request_id = None
                try:
                    body = getattr(resp, "text", None)
                except Exception:
                    body = None
            req = getattr(e, "request", None)
            if url is None and req is not None:
                try:
                    url = str(getattr(req, "url", None) or "")
                except Exception:
                    url = None
        except Exception:
            pass

        msg = "Server-side snapshot API failed"
        bits = []
        if status_code is not None:
            bits.append(f"status={status_code}")
        if url:
            bits.append(f"url={url}")
        if request_id:
            bits.append(f"request_id={request_id}")
        body_snip = cls._snip(body)
        if body_snip:
            bits.append(f"body={body_snip}")
        # If we don't have an HTTP status/response body, this is usually a transport error
        # (timeout, DNS, connection reset). Preserve at least the exception type + message.
        if status_code is None and not body_snip:
            try:
                err_s = cls._snip(str(e), 220)
            except Exception:
                err_s = None
            bits.append(f"err_type={type(e).__name__}")
            if err_s:
                bits.append(f"err={err_s}")
            else:
                # Some transport errors (e.g. httpx.ReadError) can stringify to "".
                # Include repr() so callers can still see the exception type/shape.
                try:
                    bits.append(f"err_repr={cls._snip(repr(e), 220)}")
                except Exception:
                    pass
        if bits:
            msg = f"{msg}: " + " ".join(bits)
        msg = msg + ". Try using use_api=False to use local extension instead."
        return cls(
            msg,
            status_code=int(status_code) if status_code is not None else None,
            url=url,
            request_id=str(request_id) if request_id else None,
            response_text=body_snip,
            cause=e,
        )

    @classmethod
    def from_requests(cls, e: Exception) -> "SnapshotGatewayError":
        status_code = None
        url = None
        request_id = None
        body = None
        try:
            resp = getattr(e, "response", None)
            if resp is not None:
                status_code = getattr(resp, "status_code", None)
                try:
                    url = str(getattr(resp, "url", None) or "")
                except Exception:
                    url = None
                try:
                    headers = getattr(resp, "headers", None) or {}
                    request_id = headers.get("x-request-id") or headers.get("x-trace-id")
                except Exception:
                    request_id = None
                try:
                    body = getattr(resp, "text", None)
                except Exception:
                    body = None
        except Exception:
            pass
        msg = "Server-side snapshot API failed"
        bits = []
        if status_code is not None:
            bits.append(f"status={status_code}")
        if url:
            bits.append(f"url={url}")
        if request_id:
            bits.append(f"request_id={request_id}")
        body_snip = cls._snip(body)
        if body_snip:
            bits.append(f"body={body_snip}")
        if status_code is None and not body_snip:
            try:
                err_s = cls._snip(str(e), 220)
            except Exception:
                err_s = None
            bits.append(f"err_type={type(e).__name__}")
            if err_s:
                bits.append(f"err={err_s}")
            else:
                try:
                    bits.append(f"err_repr={cls._snip(repr(e), 220)}")
                except Exception:
                    pass
        if bits:
            msg = f"{msg}: " + " ".join(bits)
        msg = msg + ". Try using use_api=False to use local extension instead."
        return cls(
            msg,
            status_code=int(status_code) if status_code is not None else None,
            url=url,
            request_id=str(request_id) if request_id else None,
            response_text=body_snip,
            cause=e,
        )


def _is_execution_context_destroyed_error(e: Exception) -> bool:
    """
    Playwright can throw while a navigation is in-flight, invalidating the JS execution context.

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


async def _page_evaluate_with_nav_retry(
    page: Any,
    expression: str,
    arg: Any = None,
    *,
    retries: int = 2,
    settle_timeout_ms: int = 10000,
) -> Any:
    """
    Evaluate JS with a small retry loop if the page is mid-navigation.

    This prevents flaky crashes when callers snapshot right after triggering a navigation
    (e.g., pressing Enter on Google).
    """
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if arg is None:
                return await page.evaluate(expression)
            return await page.evaluate(expression, arg)
        except Exception as e:
            last_err = e
            if not _is_execution_context_destroyed_error(e) or attempt >= retries:
                raise
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=settle_timeout_ms)
            except Exception:
                pass
            await asyncio.sleep(0.25)
    raise last_err if last_err else RuntimeError("Page.evaluate failed")


async def _wait_for_function_with_nav_retry(
    page: Any,
    expression: str,
    *,
    timeout_ms: int,
    retries: int = 2,
) -> None:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            await page.wait_for_function(expression, timeout=timeout_ms)
            return
        except Exception as e:
            last_err = e
            if not _is_execution_context_destroyed_error(e) or attempt >= retries:
                raise
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass
            await asyncio.sleep(0.25)
    raise last_err if last_err else RuntimeError("wait_for_function failed")


def _build_snapshot_payload(
    raw_result: dict[str, Any],
    options: SnapshotOptions,
) -> dict[str, Any]:
    """
    Build payload dict for gateway snapshot API.

    Shared helper used by both sync and async snapshot implementations.
    """
    diagnostics = raw_result.get("diagnostics") or {}
    client_metrics = None
    client_diagnostics = None
    try:
        client_metrics = diagnostics.get("metrics")
    except Exception:
        client_metrics = None
    try:
        captcha = diagnostics.get("captcha")
        requires_vision = diagnostics.get("requires_vision")
        requires_vision_reason = diagnostics.get("requires_vision_reason")
        if any(x is not None for x in [captcha, requires_vision, requires_vision_reason]):
            client_diagnostics = {}
            if captcha is not None:
                client_diagnostics["captcha"] = captcha
            if requires_vision is not None:
                client_diagnostics["requires_vision"] = bool(requires_vision)
            if requires_vision_reason is not None:
                client_diagnostics["requires_vision_reason"] = str(requires_vision_reason)
    except Exception:
        client_diagnostics = None

    return {
        "raw_elements": raw_result.get("raw_elements", []),
        "url": raw_result.get("url", ""),
        "viewport": raw_result.get("viewport"),
        "goal": options.goal,
        "options": {
            "limit": options.limit,
            "filter": options.filter.model_dump() if options.filter else None,
        },
        "client_metrics": client_metrics,
        "client_diagnostics": client_diagnostics,
    }


def _validate_payload_size(payload_json: str) -> None:
    """
    Validate payload size before sending to gateway.

    Raises ValueError if payload exceeds server limit.
    """
    payload_size = len(payload_json.encode("utf-8"))
    if payload_size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Payload size ({payload_size / 1024 / 1024:.2f}MB) exceeds server limit "
            f"({MAX_PAYLOAD_BYTES / 1024 / 1024:.0f}MB). "
            f"Try reducing the number of elements on the page or filtering elements."
        )


def _post_snapshot_to_gateway_sync(
    payload: dict[str, Any],
    api_key: str,
    api_url: str = SENTIENCE_API_URL,
    *,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """
    Post snapshot payload to gateway (synchronous).

    Used by sync snapshot() function.
    """
    payload_json = json.dumps(payload)
    _validate_payload_size(payload_json)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = 30 if timeout_s is None else float(timeout_s)
        response = requests.post(
            f"{api_url}/v1/snapshot",
            data=payload_json,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        raise SnapshotGatewayError.from_requests(e) from e
    except requests.exceptions.RequestException as e:
        # Network/timeouts/etc (no status code available)
        raise SnapshotGatewayError.from_requests(e) from e


async def _post_snapshot_to_gateway_async(
    payload: dict[str, Any],
    api_key: str,
    api_url: str = SENTIENCE_API_URL,
    *,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """
    Post snapshot payload to gateway (asynchronous).

    Used by async backend snapshot() function.
    """
    # Lazy import httpx - only needed for async API calls
    import httpx

    payload_json = json.dumps(payload)
    _validate_payload_size(payload_json)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = 30.0 if timeout_s is None else float(timeout_s)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                f"{api_url}/v1/snapshot",
                content=payload_json,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise SnapshotGatewayError.from_httpx(e) from e
        except httpx.RequestError as e:
            raise SnapshotGatewayError.from_httpx(e) from e
        except Exception as e:
            # JSON decode or other unexpected issues — keep details if possible.
            raise SnapshotGatewayError.from_httpx(e) from e


def _merge_api_result_with_local(
    api_result: dict[str, Any],
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge API result with local data (screenshot, etc.).

    Shared helper used by both sync and async snapshot implementations.
    """
    return {
        "status": api_result.get("status", "success"),
        "timestamp": api_result.get("timestamp"),
        "url": api_result.get("url", raw_result.get("url", "")),
        "viewport": api_result.get("viewport", raw_result.get("viewport")),
        "elements": api_result.get("elements", []),
        "screenshot": raw_result.get("screenshot"),  # Keep local screenshot
        "screenshot_format": raw_result.get("screenshot_format"),
        "error": api_result.get("error"),
        # Phase 2: Runtime stability/debug info
        "diagnostics": api_result.get("diagnostics", raw_result.get("diagnostics")),
        # Phase 2: Ordinal support - dominant group key from Gateway
        "dominant_group_key": api_result.get("dominant_group_key"),
    }


def _save_trace_to_file(raw_elements: list[dict[str, Any]], trace_path: str | None = None) -> None:
    """
    Save raw_elements to a JSON file for benchmarking/training

    Args:
        raw_elements: Raw elements data from snapshot
        trace_path: Path to save trace file. If None, uses "trace_{timestamp}.json"
    """
    # Default filename if none provided
    filename = trace_path or f"trace_{int(time.time())}.json"

    # Ensure directory exists
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # Save the raw elements to JSON
    with open(filename, "w") as f:
        json.dump(raw_elements, f, indent=2)

    print(f"[SDK] Trace saved to: {filename}")


def snapshot(
    browser: SentienceBrowser,
    options: SnapshotOptions | None = None,
) -> Snapshot:
    """
    Take a snapshot of the current page

    Args:
        browser: SentienceBrowser instance
        options: Snapshot options (screenshot, limit, filter, etc.)
                If None, uses default options.

    Returns:
        Snapshot object

    Example:
        # Basic snapshot with defaults
        snap = snapshot(browser)

        # With options
        snap = snapshot(browser, SnapshotOptions(
            screenshot=True,
            limit=100,
            show_overlay=True
        ))
    """
    # Use default options if none provided
    if options is None:
        options = SnapshotOptions()

    # Resolve API key: options.sentience_api_key takes precedence, then browser.api_key
    # This allows browser-use users to pass api_key via options without SentienceBrowser
    effective_api_key = options.sentience_api_key or browser.api_key

    # Determine if we should use server-side API
    should_use_api = (
        options.use_api if options.use_api is not None else (effective_api_key is not None)
    )

    if should_use_api and effective_api_key:
        # Use server-side API (Pro/Enterprise tier)
        return _snapshot_via_api(browser, options, effective_api_key)
    else:
        # Use local extension (Free tier)
        return _snapshot_via_extension(browser, options)


def _snapshot_via_extension(
    browser: SentienceBrowser,
    options: SnapshotOptions,
) -> Snapshot:
    """Take snapshot using local extension (Free tier)"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    # CRITICAL: Wait for extension injection to complete (CSP-resistant architecture)
    # The new architecture loads injected_api.js asynchronously, so window.sentience
    # may not be immediately available after page load
    BrowserEvaluator.wait_for_extension(browser.page, timeout_ms=5000)

    # Build options dict for extension API (exclude save_trace/trace_path)
    ext_options: dict[str, Any] = {}
    if options.screenshot is not False:
        # Serialize ScreenshotConfig to dict if it's a Pydantic model
        if hasattr(options.screenshot, "model_dump"):
            ext_options["screenshot"] = options.screenshot.model_dump()
        else:
            ext_options["screenshot"] = options.screenshot
    if options.limit != 50:
        ext_options["limit"] = options.limit
    if options.filter is not None:
        ext_options["filter"] = (
            options.filter.model_dump() if hasattr(options.filter, "model_dump") else options.filter
        )

    # Call extension API
    result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        ext_options,
    )

    # Save trace if requested
    if options.save_trace:
        _save_trace_to_file(result.get("raw_elements", []), options.trace_path)

    # Validate and parse with Pydantic
    snapshot_obj = Snapshot(**result)

    # Show visual overlay if requested
    if options.show_overlay:
        # Prefer processed semantic elements for overlay (have bbox/importance/visual_cues).
        # raw_elements may not match the overlay renderer's expected shape.
        elements_for_overlay = result.get("elements") or result.get("raw_elements") or []
        if elements_for_overlay:
            browser.page.evaluate(
                """
                (elements) => {
                    if (window.sentience && window.sentience.showOverlay) {
                        window.sentience.showOverlay(elements, null);
                    }
                }
                """,
                elements_for_overlay,
            )

    # Show grid overlay if requested
    if options.show_grid:
        # Get all grids (don't filter by grid_id here - we want to show all but highlight the target)
        grids = snapshot_obj.get_grid_bounds(grid_id=None)
        if grids:
            # Convert GridInfo to dict for JavaScript
            grid_dicts = [grid.model_dump() for grid in grids]
            # Pass grid_id as targetGridId to highlight it in red
            target_grid_id = options.grid_id if options.grid_id is not None else None
            browser.page.evaluate(
                """
                (grids, targetGridId) => {
                    if (window.sentience && window.sentience.showGrid) {
                        window.sentience.showGrid(grids, targetGridId);
                    } else {
                        console.warn('[SDK] showGrid not available in extension');
                    }
                }
                """,
                grid_dicts,
                target_grid_id,
            )

    return snapshot_obj


def _snapshot_via_api(
    browser: SentienceBrowser,
    options: SnapshotOptions,
    api_key: str,
) -> Snapshot:
    """Take snapshot using server-side API (Pro/Enterprise tier)"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    # Use browser.api_url if set, otherwise default
    api_url = browser.api_url or SENTIENCE_API_URL

    # CRITICAL: Wait for extension injection to complete (CSP-resistant architecture)
    # Even for API mode, we need the extension to collect raw data locally
    BrowserEvaluator.wait_for_extension(browser.page, timeout_ms=5000)

    # Step 1: Get raw data from local extension (always happens locally)
    raw_options: dict[str, Any] = {}
    if options.screenshot is not False:
        raw_options["screenshot"] = options.screenshot
    # Important: also pass limit/filter to extension to keep raw_elements payload bounded.
    # Without this, large pages (e.g. Amazon) can exceed gateway request size limits (HTTP 413).
    if options.limit != 50:
        raw_options["limit"] = options.limit
    if options.filter is not None:
        raw_options["filter"] = (
            options.filter.model_dump() if hasattr(options.filter, "model_dump") else options.filter
        )

    raw_result = BrowserEvaluator.invoke(browser.page, SentienceMethod.SNAPSHOT, **raw_options)

    # Save trace if requested (save raw data before API processing)
    if options.save_trace:
        _save_trace_to_file(raw_result.get("raw_elements", []), options.trace_path)

    # Step 2: Send to server for smart ranking/filtering
    # Use raw_elements (raw data) instead of elements (processed data)
    # Server validates API key and applies proprietary ranking logic
    payload = _build_snapshot_payload(raw_result, options)

    try:
        api_result = _post_snapshot_to_gateway_sync(
            payload,
            api_key,
            api_url,
            timeout_s=options.gateway_timeout_s,
        )

        # Merge API result with local data (screenshot, etc.)
        snapshot_data = _merge_api_result_with_local(api_result, raw_result)

        # Create snapshot object
        snapshot_obj = Snapshot(**snapshot_data)

        # Show visual overlay if requested (use API-ranked elements)
        if options.show_overlay:
            elements = api_result.get("elements", [])
            if elements:
                browser.page.evaluate(
                    """
                    (elements) => {
                        if (window.sentience && window.sentience.showOverlay) {
                            window.sentience.showOverlay(elements, null);
                        }
                    }
                    """,
                    elements,
                )

        # Show grid overlay if requested
        if options.show_grid:
            # Get all grids (don't filter by grid_id here - we want to show all but highlight the target)
            grids = snapshot_obj.get_grid_bounds(grid_id=None)
            if grids:
                grid_dicts = [grid.model_dump() for grid in grids]
                # Pass grid_id as targetGridId to highlight it in red
                target_grid_id = options.grid_id if options.grid_id is not None else None
                browser.page.evaluate(
                    """
                    (grids, targetGridId) => {
                        if (window.sentience && window.sentience.showGrid) {
                            window.sentience.showGrid(grids, targetGridId);
                        } else {
                            console.warn('[SDK] showGrid not available in extension');
                        }
                    }
                    """,
                    grid_dicts,
                    target_grid_id,
                )

        return snapshot_obj
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API request failed: {e}") from e


# ========== Async Snapshot Functions ==========


async def snapshot_async(
    browser: AsyncSentienceBrowser,
    options: SnapshotOptions | None = None,
) -> Snapshot:
    """
    Take a snapshot of the current page (async)

    Args:
        browser: AsyncSentienceBrowser instance
        options: Snapshot options (screenshot, limit, filter, etc.)
                If None, uses default options.

    Returns:
        Snapshot object

    Example:
        # Basic snapshot with defaults
        snap = await snapshot_async(browser)

        # With options
        snap = await snapshot_async(browser, SnapshotOptions(
            screenshot=True,
            limit=100,
            show_overlay=True
        ))
    """
    # Use default options if none provided
    if options is None:
        options = SnapshotOptions()

    # Resolve API key: options.sentience_api_key takes precedence, then browser.api_key
    # This allows browser-use users to pass api_key via options without SentienceBrowser
    effective_api_key = options.sentience_api_key or browser.api_key

    # Determine if we should use server-side API
    should_use_api = (
        options.use_api if options.use_api is not None else (effective_api_key is not None)
    )

    if should_use_api and effective_api_key:
        # Use server-side API (Pro/Enterprise tier)
        return await _snapshot_via_api_async(browser, options, effective_api_key)
    else:
        # Use local extension (Free tier)
        return await _snapshot_via_extension_async(browser, options)


async def _snapshot_via_extension_async(
    browser: AsyncSentienceBrowser,
    options: SnapshotOptions,
) -> Snapshot:
    """Take snapshot using local extension (Free tier) - async"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    # Wait for extension injection to complete
    try:
        await _wait_for_function_with_nav_retry(
            browser.page,
            "typeof window.sentience !== 'undefined'",
            timeout_ms=5000,
        )
    except Exception as e:
        try:
            diag = await _page_evaluate_with_nav_retry(
                browser.page,
                """() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })""",
            )
        except Exception:
            diag = {"error": "Could not gather diagnostics"}

        raise RuntimeError(
            f"Sentience extension failed to inject window.sentience API. "
            f"Is the extension loaded? Diagnostics: {diag}"
        ) from e

    # Build options dict for extension API
    ext_options: dict[str, Any] = {}
    if options.screenshot is not False:
        # Serialize ScreenshotConfig to dict if it's a Pydantic model
        if hasattr(options.screenshot, "model_dump"):
            ext_options["screenshot"] = options.screenshot.model_dump()
        else:
            ext_options["screenshot"] = options.screenshot
    if options.limit != 50:
        ext_options["limit"] = options.limit
    if options.filter is not None:
        ext_options["filter"] = (
            options.filter.model_dump() if hasattr(options.filter, "model_dump") else options.filter
        )

    # Call extension API
    result = await _page_evaluate_with_nav_retry(
        browser.page,
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        ext_options,
    )
    if result.get("error"):
        print(f"      Snapshot error: {result.get('error')}")

    # Save trace if requested
    if options.save_trace:
        _save_trace_to_file(result.get("raw_elements", []), options.trace_path)

    # Extract screenshot_format from data URL if not provided by extension
    if result.get("screenshot") and not result.get("screenshot_format"):
        screenshot_data_url = result.get("screenshot", "")
        if screenshot_data_url.startswith("data:image/"):
            # Extract format from "data:image/jpeg;base64,..." or "data:image/png;base64,..."
            format_match = screenshot_data_url.split(";")[0].split("/")[-1]
            if format_match in ["jpeg", "jpg", "png"]:
                result["screenshot_format"] = "jpeg" if format_match in ["jpeg", "jpg"] else "png"

    # Validate and parse with Pydantic
    snapshot_obj = Snapshot(**result)

    # Show visual overlay if requested
    if options.show_overlay:
        # Prefer processed semantic elements for overlay (have bbox/importance/visual_cues).
        # raw_elements may not match the overlay renderer's expected shape.
        elements_for_overlay = result.get("elements") or result.get("raw_elements") or []
        if elements_for_overlay:
            await _page_evaluate_with_nav_retry(
                browser.page,
                """
                (elements) => {
                    if (window.sentience && window.sentience.showOverlay) {
                        window.sentience.showOverlay(elements, null);
                    }
                }
                """,
                elements_for_overlay,
            )

    # Show grid overlay if requested
    if options.show_grid:
        # Get all grids (don't filter by grid_id here - we want to show all but highlight the target)
        grids = snapshot_obj.get_grid_bounds(grid_id=None)
        if grids:
            grid_dicts = [grid.model_dump() for grid in grids]
            # Pass grid_id as targetGridId to highlight it in red
            target_grid_id = options.grid_id if options.grid_id is not None else None
            await _page_evaluate_with_nav_retry(
                browser.page,
                """
                (args) => {
                    const [grids, targetGridId] = args;
                    if (window.sentience && window.sentience.showGrid) {
                        window.sentience.showGrid(grids, targetGridId);
                    } else {
                        console.warn('[SDK] showGrid not available in extension');
                    }
                }
                """,
                [grid_dicts, target_grid_id],
            )

    return snapshot_obj


async def _snapshot_via_api_async(
    browser: AsyncSentienceBrowser,
    options: SnapshotOptions,
    api_key: str,
) -> Snapshot:
    """Take snapshot using server-side API (Pro/Enterprise tier) - async"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    # Use browser.api_url if set, otherwise default
    api_url = browser.api_url or SENTIENCE_API_URL

    # Wait for extension injection
    try:
        await _wait_for_function_with_nav_retry(
            browser.page,
            "typeof window.sentience !== 'undefined'",
            timeout_ms=5000,
        )
    except Exception as e:
        raise RuntimeError(
            "Sentience extension failed to inject. Cannot collect raw data for API processing."
        ) from e

    # Step 1: Get raw data from local extension (including screenshot)
    raw_options: dict[str, Any] = {}
    screenshot_requested = False
    if options.screenshot is not False:
        screenshot_requested = True
        # Serialize ScreenshotConfig to dict if it's a Pydantic model
        if hasattr(options.screenshot, "model_dump"):
            raw_options["screenshot"] = options.screenshot.model_dump()
        else:
            raw_options["screenshot"] = options.screenshot
    # Important: also pass limit/filter to extension to keep raw_elements payload bounded.
    # Without this, large pages (e.g. Amazon) can exceed gateway request size limits (HTTP 413).
    if options.limit != 50:
        raw_options["limit"] = options.limit
    if options.filter is not None:
        raw_options["filter"] = (
            options.filter.model_dump() if hasattr(options.filter, "model_dump") else options.filter
        )

    raw_result = await _page_evaluate_with_nav_retry(
        browser.page,
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        raw_options,
    )

    # Extract screenshot from raw result (extension captures it, but API doesn't return it)
    screenshot_data_url = raw_result.get("screenshot")
    screenshot_format = None
    if screenshot_data_url:
        # Extract format from data URL
        if screenshot_data_url.startswith("data:image/"):
            format_match = screenshot_data_url.split(";")[0].split("/")[-1]
            if format_match in ["jpeg", "jpg", "png"]:
                screenshot_format = "jpeg" if format_match in ["jpeg", "jpg"] else "png"

    # Save trace if requested
    if options.save_trace:
        _save_trace_to_file(raw_result.get("raw_elements", []), options.trace_path)

    # Step 2: Send to server for smart ranking/filtering
    payload = {
        "raw_elements": raw_result.get("raw_elements", []),
        "url": raw_result.get("url", ""),
        "viewport": raw_result.get("viewport"),
        "goal": options.goal,
        "options": {
            "limit": options.limit,
            "filter": options.filter.model_dump() if options.filter else None,
        },
    }

    # Check payload size
    payload_json = json.dumps(payload)
    payload_size = len(payload_json.encode("utf-8"))
    if payload_size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Payload size ({payload_size / 1024 / 1024:.2f}MB) exceeds server limit "
            f"({MAX_PAYLOAD_BYTES / 1024 / 1024:.0f}MB). "
            f"Try reducing the number of elements on the page or filtering elements."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        # Lazy import httpx - only needed for async API calls
        import httpx

        timeout = 30.0 if options.gateway_timeout_s is None else float(options.gateway_timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{api_url}/v1/snapshot",
                content=payload_json,
                headers=headers,
            )
            response.raise_for_status()
            api_result = response.json()

        # Extract screenshot format from data URL if not provided
        if screenshot_data_url and not screenshot_format:
            if screenshot_data_url.startswith("data:image/"):
                format_match = screenshot_data_url.split(";")[0].split("/")[-1]
                if format_match in ["jpeg", "jpg", "png"]:
                    screenshot_format = "jpeg" if format_match in ["jpeg", "jpg"] else "png"

        # Merge API result with local data
        snapshot_data = {
            "status": api_result.get("status", "success"),
            "timestamp": api_result.get("timestamp"),
            "url": api_result.get("url", raw_result.get("url", "")),
            "viewport": api_result.get("viewport", raw_result.get("viewport")),
            "elements": api_result.get("elements", []),
            "screenshot": screenshot_data_url,  # Use the extracted screenshot
            "screenshot_format": screenshot_format,  # Use the extracted format
            "error": api_result.get("error"),
        }

        # Create snapshot object
        snapshot_obj = Snapshot(**snapshot_data)

        # Show visual overlay if requested
        if options.show_overlay:
            elements = api_result.get("elements", [])
            if elements:
                await _page_evaluate_with_nav_retry(
                    browser.page,
                    """
                    (elements) => {
                        if (window.sentience && window.sentience.showOverlay) {
                            window.sentience.showOverlay(elements, null);
                        }
                    }
                    """,
                    elements,
                )

        # Show grid overlay if requested
        if options.show_grid:
            # Get all grids (don't filter by grid_id here - we want to show all but highlight the target)
            grids = snapshot_obj.get_grid_bounds(grid_id=None)
            if grids:
                grid_dicts = [grid.model_dump() for grid in grids]
                # Pass grid_id as targetGridId to highlight it in red
                target_grid_id = options.grid_id if options.grid_id is not None else None
                await _page_evaluate_with_nav_retry(
                    browser.page,
                    """
                    (args) => {
                        const [grids, targetGridId] = args;
                        if (window.sentience && window.sentience.showGrid) {
                            window.sentience.showGrid(grids, targetGridId);
                        } else {
                            console.warn('[SDK] showGrid not available in extension');
                        }
                    }
                    """,
                    [grid_dicts, target_grid_id],
                )

        return snapshot_obj
    except ImportError:
        # Fallback to requests if httpx not available (shouldn't happen in async context)
        raise RuntimeError(
            "httpx is required for async API calls. Install it with: pip install httpx"
        )
    except Exception as e:
        raise RuntimeError(f"API request failed: {e}")
