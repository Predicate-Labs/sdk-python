"""
Snapshot functionality - calls window.sentience.snapshot() or server-side API
"""

from typing import Optional, Dict, Any
import json
import requests
from .browser import SentienceBrowser
from .models import Snapshot


def snapshot(
    browser: SentienceBrowser,
    screenshot: Optional[bool] = None,
    limit: Optional[int] = None,
    filter: Optional[Dict[str, Any]] = None,
    use_api: Optional[bool] = None,
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
    
    Returns:
        Snapshot object
    """
    # Determine if we should use server-side API
    should_use_api = use_api if use_api is not None else (browser.api_key is not None)
    
    if should_use_api and browser.api_key:
        # Use server-side API (Pro/Enterprise tier)
        return _snapshot_via_api(browser, screenshot, limit, filter)
    else:
        # Use local extension (Free tier)
        return _snapshot_via_extension(browser, screenshot, limit, filter)


def _snapshot_via_extension(
    browser: SentienceBrowser,
    screenshot: Optional[bool],
    limit: Optional[int],
    filter: Optional[Dict[str, Any]],
) -> Snapshot:
    """Take snapshot using local extension (Free tier)"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    
    # Build options
    options: Dict[str, Any] = {}
    if screenshot is not None:
        options["screenshot"] = screenshot
    if limit is not None:
        options["limit"] = limit
    if filter is not None:
        options["filter"] = filter
    
    # Call extension API
    result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        options,
    )
    
    # Validate and parse with Pydantic
    snapshot_obj = Snapshot(**result)
    return snapshot_obj


def _snapshot_via_api(
    browser: SentienceBrowser,
    screenshot: Optional[bool],
    limit: Optional[int],
    filter: Optional[Dict[str, Any]],
) -> Snapshot:
    """Take snapshot using server-side API (Pro/Enterprise tier)"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    
    if not browser.api_key:
        raise ValueError("API key required for server-side processing")
    
    if not browser.api_url:
        raise ValueError("API URL required for server-side processing")
    
    # Step 1: Get raw data from local extension (always happens locally)
    raw_options: Dict[str, Any] = {}
    if screenshot is not None:
        raw_options["screenshot"] = screenshot
    
    raw_result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        raw_options,
    )
    
    # Step 2: Send to server for smart ranking/filtering
    # Use raw_elements (raw data) instead of elements (processed data)
    # Server validates API key and applies proprietary ranking logic
    payload = {
        "raw_elements": raw_result.get("raw_elements", []),  # Raw data needed for server processing
        "url": raw_result.get("url", ""),
        "viewport": raw_result.get("viewport"),
        "options": {
            "limit": limit,
            "filter": filter,
        }
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
        
        return Snapshot(**snapshot_data)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API request failed: {e}")

