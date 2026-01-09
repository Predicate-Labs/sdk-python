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
from .models import Snapshot, SnapshotOptions
from .sentience_methods import SentienceMethod

# Maximum payload size for API requests (10MB server limit)
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024


def _build_snapshot_payload(
    raw_result: dict[str, Any],
    options: SnapshotOptions,
) -> dict[str, Any]:
    """
    Build payload dict for gateway snapshot API.

    Shared helper used by both sync and async snapshot implementations.
    """
    return {
        "raw_elements": raw_result.get("raw_elements", []),
        "url": raw_result.get("url", ""),
        "viewport": raw_result.get("viewport"),
        "goal": options.goal,
        "options": {
            "limit": options.limit,
            "filter": options.filter.model_dump() if options.filter else None,
        },
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
    api_url: str = "https://api.sentienceapi.com",
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

    response = requests.post(
        f"{api_url}/v1/snapshot",
        data=payload_json,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


async def _post_snapshot_to_gateway_async(
    payload: dict[str, Any],
    api_key: str,
    api_url: str = "https://api.sentienceapi.com",
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

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{api_url}/v1/snapshot",
            content=payload_json,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


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

    # Show visual overlay if requested
    if options.show_overlay:
        raw_elements = result.get("raw_elements", [])
        if raw_elements:
            browser.page.evaluate(
                """
                (elements) => {
                    if (window.sentience && window.sentience.showOverlay) {
                        window.sentience.showOverlay(elements, null);
                    }
                }
                """,
                raw_elements,
            )

    # Validate and parse with Pydantic
    snapshot_obj = Snapshot(**result)
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
    api_url = browser.api_url or "https://api.sentienceapi.com"

    # CRITICAL: Wait for extension injection to complete (CSP-resistant architecture)
    # Even for API mode, we need the extension to collect raw data locally
    BrowserEvaluator.wait_for_extension(browser.page, timeout_ms=5000)

    # Step 1: Get raw data from local extension (always happens locally)
    raw_options: dict[str, Any] = {}
    if options.screenshot is not False:
        raw_options["screenshot"] = options.screenshot

    raw_result = BrowserEvaluator.invoke(browser.page, SentienceMethod.SNAPSHOT, **raw_options)

    # Save trace if requested (save raw data before API processing)
    if options.save_trace:
        _save_trace_to_file(raw_result.get("raw_elements", []), options.trace_path)

    # Step 2: Send to server for smart ranking/filtering
    # Use raw_elements (raw data) instead of elements (processed data)
    # Server validates API key and applies proprietary ranking logic
    payload = _build_snapshot_payload(raw_result, options)

    try:
        api_result = _post_snapshot_to_gateway_sync(payload, api_key, api_url)

        # Merge API result with local data (screenshot, etc.)
        snapshot_data = _merge_api_result_with_local(api_result, raw_result)

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

        return Snapshot(**snapshot_data)
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
        await browser.page.wait_for_function(
            "typeof window.sentience !== 'undefined'",
            timeout=5000,
        )
    except Exception as e:
        try:
            diag = await browser.page.evaluate(
                """() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })"""
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
    result = await browser.page.evaluate(
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

    # Show visual overlay if requested
    if options.show_overlay:
        raw_elements = result.get("raw_elements", [])
        if raw_elements:
            await browser.page.evaluate(
                """
                (elements) => {
                    if (window.sentience && window.sentience.showOverlay) {
                        window.sentience.showOverlay(elements, null);
                    }
                }
                """,
                raw_elements,
            )

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
    api_url = browser.api_url or "https://api.sentienceapi.com"

    # Wait for extension injection
    try:
        await browser.page.wait_for_function(
            "typeof window.sentience !== 'undefined'", timeout=5000
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

    raw_result = await browser.page.evaluate(
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

        async with httpx.AsyncClient(timeout=30.0) as client:
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

        # Show visual overlay if requested
        if options.show_overlay:
            elements = api_result.get("elements", [])
            if elements:
                await browser.page.evaluate(
                    """
                    (elements) => {
                        if (window.sentience && window.sentience.showOverlay) {
                            window.sentience.showOverlay(elements, null);
                        }
                    }
                    """,
                    elements,
                )

        return Snapshot(**snapshot_data)
    except ImportError:
        # Fallback to requests if httpx not available (shouldn't happen in async context)
        raise RuntimeError(
            "httpx is required for async API calls. Install it with: pip install httpx"
        )
    except Exception as e:
        raise RuntimeError(f"API request failed: {e}")
