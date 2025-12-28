"""
Snapshot functionality - calls window.sentience.snapshot() or server-side API
"""

import json
import os
import time
from typing import Any

import requests

from .browser import SentienceBrowser
from .models import Snapshot, SnapshotOptions


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
    screenshot: bool | None = None,
    limit: int | None = None,
    filter: dict[str, Any] | None = None,
    use_api: bool | None = None,
    save_trace: bool = False,
    trace_path: str | None = None,
    show_overlay: bool = False,
) -> Snapshot:
    """
    Take a snapshot of the current page

    Args:
        browser: SentienceBrowser instance
        screenshot: Whether to capture screenshot (bool or dict with format/quality)
        limit: Limit number of elements returned
        filter: Filter options (min_area, allowed_roles, min_z_index)
        use_api: Force use of server-side API if True, local extension if False.
                 If None, uses API if api_key is set, otherwise uses local extension.
        save_trace: Whether to save raw_elements to JSON for benchmarking/training
        trace_path: Path to save trace file. If None, uses "trace_{timestamp}.json"
        show_overlay: Show visual overlay highlighting elements in browser

    Returns:
        Snapshot object
    """
    # Build SnapshotOptions from individual parameters
    options = SnapshotOptions(
        screenshot=screenshot if screenshot is not None else False,
        limit=limit if limit is not None else 50,
        filter=filter,
        use_api=use_api,
        save_trace=save_trace,
        trace_path=trace_path,
        show_overlay=show_overlay,
    )

    # Determine if we should use server-side API
    should_use_api = (
        options.use_api if options.use_api is not None else (browser.api_key is not None)
    )

    if should_use_api and browser.api_key:
        # Use server-side API (Pro/Enterprise tier)
        return _snapshot_via_api(browser, options)
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
    try:
        browser.page.wait_for_function(
            "typeof window.sentience !== 'undefined'",
            timeout=5000,  # 5 second timeout
        )
    except Exception as e:
        # Gather diagnostics if wait fails
        try:
            diag = browser.page.evaluate(
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

    # Build options dict for extension API (exclude save_trace/trace_path)
    ext_options: dict[str, Any] = {}
    if options.screenshot is not False:
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
) -> Snapshot:
    """Take snapshot using server-side API (Pro/Enterprise tier)"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    if not browser.api_key:
        raise ValueError("API key required for server-side processing")

    if not browser.api_url:
        raise ValueError("API URL required for server-side processing")

    # CRITICAL: Wait for extension injection to complete (CSP-resistant architecture)
    # Even for API mode, we need the extension to collect raw data locally
    try:
        browser.page.wait_for_function("typeof window.sentience !== 'undefined'", timeout=5000)
    except Exception as e:
        raise RuntimeError(
            "Sentience extension failed to inject. Cannot collect raw data for API processing."
        ) from e

    # Step 1: Get raw data from local extension (always happens locally)
    raw_options: dict[str, Any] = {}
    if options.screenshot is not False:
        raw_options["screenshot"] = options.screenshot

    raw_result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        raw_options,
    )

    # Save trace if requested (save raw data before API processing)
    if options.save_trace:
        _save_trace_to_file(raw_result.get("raw_elements", []), options.trace_path)

    # Step 2: Send to server for smart ranking/filtering
    # Use raw_elements (raw data) instead of elements (processed data)
    # Server validates API key and applies proprietary ranking logic
    payload = {
        "raw_elements": raw_result.get("raw_elements", []),  # Raw data needed for server processing
        "url": raw_result.get("url", ""),
        "viewport": raw_result.get("viewport"),
        "goal": options.goal,  # Optional goal/task description
        "options": {
            "limit": options.limit,
            "filter": options.filter.model_dump() if options.filter else None,
        },
    }

    headers = {
        "Authorization": f"Bearer {browser.api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{browser.api_url}/v1/snapshot",
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        api_result = response.json()

        # Merge API result with local data (screenshot, etc.)
        snapshot_data = {
            "status": api_result.get("status", "success"),
            "timestamp": api_result.get("timestamp"),
            "url": api_result.get("url", raw_result.get("url", "")),
            "viewport": api_result.get("viewport", raw_result.get("viewport")),
            "elements": api_result.get("elements", []),
            "screenshot": raw_result.get("screenshot"),  # Keep local screenshot
            "screenshot_format": raw_result.get("screenshot_format"),
            "error": api_result.get("error"),
        }

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
        raise RuntimeError(f"API request failed: {e}")
