"""
Snapshot functionality - calls window.sentience.snapshot()
"""

from typing import Optional, Dict, Any
from .browser import SentienceBrowser
from .models import Snapshot


def snapshot(
    browser: SentienceBrowser,
    screenshot: Optional[bool] = None,
    limit: Optional[int] = None,
    filter: Optional[Dict[str, Any]] = None,
    license_key: Optional[str] = None,
) -> Snapshot:
    """
    Take a snapshot of the current page
    
    Args:
        browser: SentienceBrowser instance
        screenshot: Whether to capture screenshot (bool or dict with format/quality)
        limit: Limit number of elements returned
        filter: Filter options (min_area, allowed_roles, min_z_index)
        license_key: License key for headless mode (uses browser's if not provided)
    
    Returns:
        Snapshot object
    """
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
    
    # Use provided license_key or browser's default
    license_key = license_key or browser.license_key
    if license_key:
        options["license_key"] = license_key
    
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

