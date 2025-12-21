"""
Wait functionality - wait_for element matching selector
"""

import time
from typing import Union, Optional
from .browser import SentienceBrowser
from .models import WaitResult, Element
from .snapshot import snapshot
from .query import find


def wait_for(
    browser: SentienceBrowser,
    selector: Union[str, dict],
    timeout: float = 10.0,
    interval: float = 0.25,
) -> WaitResult:
    """
    Wait for element matching selector to appear
    
    Args:
        browser: SentienceBrowser instance
        selector: String DSL or dict query
        timeout: Maximum time to wait (seconds)
        interval: Polling interval (seconds)
    
    Returns:
        WaitResult
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Take snapshot
        snap = snapshot(browser)
        
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

