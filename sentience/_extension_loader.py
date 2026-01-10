"""
Shared extension loading logic for sync and async implementations.

Provides:
- get_extension_dir(): Returns path to bundled extension (for browser-use integration)
- verify_extension_injected(): Verifies window.sentience API is available
- get_extension_version(): Gets extension version from manifest
- verify_extension_version(): Checks SDK-extension version compatibility
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .protocols import AsyncPageProtocol, PageProtocol


def find_extension_path() -> Path:
    """
    Find Sentience extension directory (shared logic for sync and async).

    Checks multiple locations:
    1. sentience/extension/ (installed package)
    2. ../sentience-chrome (development/monorepo)

    Returns:
        Path to extension directory

    Raises:
        FileNotFoundError: If extension not found in any location
    """
    # 1. Try relative to this file (installed package structure)
    # sentience/_extension_loader.py -> sentience/extension/
    package_ext_path = Path(__file__).parent / "extension"

    # 2. Try development root (if running from source repo)
    # sentience/_extension_loader.py -> ../sentience-chrome
    dev_ext_path = Path(__file__).parent.parent.parent / "sentience-chrome"

    if package_ext_path.exists() and (package_ext_path / "manifest.json").exists():
        return package_ext_path
    elif dev_ext_path.exists() and (dev_ext_path / "manifest.json").exists():
        return dev_ext_path
    else:
        raise FileNotFoundError(
            f"Extension not found. Checked:\n"
            f"1. {package_ext_path}\n"
            f"2. {dev_ext_path}\n"
            "Make sure the extension is built and 'sentience/extension' directory exists."
        )


def get_extension_dir() -> str:
    """
    Get path to the bundled Sentience extension directory.

    Use this to load the extension into browser-use or other Chromium-based browsers:

        from sentience import get_extension_dir
        from browser_use import BrowserSession, BrowserProfile

        profile = BrowserProfile(
            args=[f"--load-extension={get_extension_dir()}"],
        )
        session = BrowserSession(browser_profile=profile)

    Returns:
        Absolute path to extension directory as string

    Raises:
        FileNotFoundError: If extension not found in package
    """
    return str(find_extension_path())


def get_extension_version() -> str:
    """
    Get the version of the bundled extension from manifest.json.

    Returns:
        Version string (e.g., "2.2.0")

    Raises:
        FileNotFoundError: If extension or manifest not found
    """
    ext_path = find_extension_path()
    manifest_path = ext_path / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    return manifest.get("version", "unknown")


def verify_extension_injected(page: "PageProtocol") -> bool:
    """
    Verify the Sentience extension injected window.sentience API (sync).

    Call this after navigating to a page to confirm the extension is working:

        browser.goto("https://example.com")
        if not verify_extension_injected(browser.page):
            raise RuntimeError("Extension not injected")

    Args:
        page: Playwright Page object (sync)

    Returns:
        True if window.sentience.snapshot is available, False otherwise
    """
    try:
        result = page.evaluate(
            "(() => !!(window.sentience && typeof window.sentience.snapshot === 'function'))()"
        )
        return bool(result)
    except Exception:
        return False


async def verify_extension_injected_async(page: "AsyncPageProtocol") -> bool:
    """
    Verify the Sentience extension injected window.sentience API (async).

    Call this after navigating to a page to confirm the extension is working:

        await browser.goto("https://example.com")
        if not await verify_extension_injected_async(browser.page):
            raise RuntimeError("Extension not injected")

    Args:
        page: Playwright Page object (async)

    Returns:
        True if window.sentience.snapshot is available, False otherwise
    """
    try:
        result = await page.evaluate(
            "(() => !!(window.sentience && typeof window.sentience.snapshot === 'function'))()"
        )
        return bool(result)
    except Exception:
        return False


def verify_extension_version(page: "PageProtocol", expected: str | None = None) -> str | None:
    """
    Check extension version exposed in page (sync).

    The extension sets window.__SENTIENCE_EXTENSION_VERSION__ when injected.

    Args:
        page: Playwright Page object (sync)
        expected: If provided, raises RuntimeError on mismatch

    Returns:
        Version string if found, None if not set (page may not have injected yet)

    Raises:
        RuntimeError: If expected version provided and doesn't match
    """
    try:
        got = page.evaluate("window.__SENTIENCE_EXTENSION_VERSION__ || null")
    except Exception:
        got = None

    if expected and got and got != expected:
        raise RuntimeError(f"Sentience extension version mismatch: expected {expected}, got {got}")
    return got


async def verify_extension_version_async(
    page: "AsyncPageProtocol", expected: str | None = None
) -> str | None:
    """
    Check extension version exposed in page (async).

    The extension sets window.__SENTIENCE_EXTENSION_VERSION__ when injected.

    Args:
        page: Playwright Page object (async)
        expected: If provided, raises RuntimeError on mismatch

    Returns:
        Version string if found, None if not set (page may not have injected yet)

    Raises:
        RuntimeError: If expected version provided and doesn't match
    """
    try:
        got = await page.evaluate("window.__SENTIENCE_EXTENSION_VERSION__ || null")
    except Exception:
        got = None

    if expected and got and got != expected:
        raise RuntimeError(f"Sentience extension version mismatch: expected {expected}, got {got}")
    return got
