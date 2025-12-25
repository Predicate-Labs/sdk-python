"""
Wait functionality - wait_for element matching selector
"""

import time
from typing import Optional, Union

from .browser import SentienceBrowser
from .models import WaitResult
from .query import find
from .snapshot import snapshot


def wait_for(
    browser: SentienceBrowser,
    selector: str | dict,
    timeout: float = 10.0,
    interval: float | None = None,
    use_api: bool | None = None,
) -> WaitResult:
    """
    Wait for element matching selector to appear

    Args:
        browser: SentienceBrowser instance
        selector: String DSL or dict query
        timeout: Maximum time to wait (seconds)
        interval: Polling interval (seconds). If None, auto-detects:
                  - 0.25s for local extension (use_api=False, fast)
                  - 1.5s for remote API (use_api=True or default, network latency)
        use_api: Force use of server-side API if True, local extension if False.
                 If None, uses API if api_key is set, otherwise uses local extension.

    Returns:
        WaitResult
    """
    # Auto-detect optimal interval based on API usage
    if interval is None:
        # Determine if using API
        will_use_api = use_api if use_api is not None else (browser.api_key is not None)
        if will_use_api:
            interval = 1.5  # Longer interval for API calls (network latency)
        else:
            interval = 0.25  # Shorter interval for local extension (fast)

    start_time = time.time()

    while time.time() - start_time < timeout:
        # Take snapshot (may be local extension or remote API)
        snap = snapshot(browser, use_api=use_api)

        # Try to find element
        element = find(snap, selector)

        if element:
            duration_ms = int((time.time() - start_time) * 1000)
            return WaitResult(
                found=True,
                element=element,
                duration_ms=duration_ms,
                timeout=False,
            )

        # Wait before next poll
        time.sleep(interval)

    # Timeout
    duration_ms = int((time.time() - start_time) * 1000)
    return WaitResult(
        found=False,
        element=None,
        duration_ms=duration_ms,
        timeout=True,
    )
