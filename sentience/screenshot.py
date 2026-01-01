"""
Screenshot functionality - standalone screenshot capture
"""

import base64
from typing import Any, Literal

from .browser import AsyncSentienceBrowser, SentienceBrowser


def screenshot(
    browser: SentienceBrowser,
    format: Literal["png", "jpeg"] = "png",
    quality: int | None = None,
) -> str:
    """
    Capture screenshot of current page

    Args:
        browser: SentienceBrowser instance
        format: Image format - "png" or "jpeg"
        quality: JPEG quality (1-100), only used for JPEG format

    Returns:
        Base64-encoded screenshot data URL (e.g., "data:image/png;base64,...")

    Raises:
        RuntimeError: If browser not started
        ValueError: If quality is invalid for JPEG
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    if format == "jpeg" and quality is not None:
        if not (1 <= quality <= 100):
            raise ValueError("Quality must be between 1 and 100 for JPEG format")

    # Use Playwright's screenshot with base64 encoding
    screenshot_options: dict[str, Any] = {
        "type": format,
    }

    if format == "jpeg" and quality is not None:
        screenshot_options["quality"] = quality

    # Capture screenshot as base64
    # Playwright returns bytes when encoding is not specified, so we encode manually
    import base64

    image_bytes = browser.page.screenshot(**screenshot_options)
    base64_data = base64.b64encode(image_bytes).decode("utf-8")

    # Return as data URL
    mime_type = "image/png" if format == "png" else "image/jpeg"
    return f"data:{mime_type};base64,{base64_data}"


async def screenshot_async(
    browser: AsyncSentienceBrowser,
    format: Literal["png", "jpeg"] = "png",
    quality: int | None = None,
) -> str:
    """
    Capture screenshot of current page (async)

    Args:
        browser: AsyncSentienceBrowser instance
        format: Image format - "png" or "jpeg"
        quality: JPEG quality (1-100), only used for JPEG format

    Returns:
        Base64-encoded screenshot data URL (e.g., "data:image/png;base64,...")

    Raises:
        RuntimeError: If browser not started
        ValueError: If quality is invalid for JPEG
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    if format == "jpeg" and quality is not None:
        if not (1 <= quality <= 100):
            raise ValueError("Quality must be between 1 and 100 for JPEG format")

    # Use Playwright's screenshot with base64 encoding
    screenshot_options: dict[str, Any] = {
        "type": format,
    }

    if format == "jpeg" and quality is not None:
        screenshot_options["quality"] = quality

    # Capture screenshot as base64
    # Playwright returns bytes when encoding is not specified, so we encode manually
    image_bytes = await browser.page.screenshot(**screenshot_options)
    base64_data = base64.b64encode(image_bytes).decode("utf-8")

    # Return as data URL
    mime_type = "image/png" if format == "png" else "image/jpeg"
    return f"data:{mime_type};base64,{base64_data}"
