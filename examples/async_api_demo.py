"""
Example: Using Async API for asyncio contexts

This example demonstrates how to use the Sentience SDK's async API
when working with asyncio, FastAPI, or other async frameworks.

To run this example:
    python -m examples.async_api_demo

Or if sentience is installed:
    python examples/async_api_demo.py
"""

import asyncio
import os

# Import async API functions
from predicate.async_api import (
    AsyncSentienceBrowser,
    click_async,
    find,
    press_async,
    snapshot_async,
    type_text_async,
)
from predicate.models import SnapshotOptions, Viewport


async def basic_async_example():
    """Basic async browser usage with context manager"""
    api_key = os.environ.get("SENTIENCE_API_KEY")

    # Use async context manager
    async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to a page
        await browser.goto("https://example.com")

        # Take a snapshot (async)
        snap = await snapshot_async(browser)
        print(f"✅ Found {len(snap.elements)} elements on the page")

        # Find an element
        link = find(snap, "role=link")
        if link:
            print(f"Found link: {link.text} (id: {link.id})")

            # Click it (async)
            result = await click_async(browser, link.id)
            print(f"Click result: success={result.success}, outcome={result.outcome}")


async def custom_viewport_example():
    """Example using custom viewport with Viewport class"""
    # Use Viewport class for type safety
    custom_viewport = Viewport(width=1920, height=1080)

    async with AsyncSentienceBrowser(viewport=custom_viewport, headless=False) as browser:
        await browser.goto("https://example.com")

        # Verify viewport size
        viewport_size = await browser.page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )
        print(f"✅ Viewport: {viewport_size['width']}x{viewport_size['height']}")


async def snapshot_with_options_example():
    """Example using SnapshotOptions with async API"""
    async with AsyncSentienceBrowser(headless=False) as browser:
        await browser.goto("https://example.com")

        # Take snapshot with options
        options = SnapshotOptions(
            limit=10,
            screenshot=False,
            show_overlay=False,
        )
        snap = await snapshot_async(browser, options)
        print(f"✅ Snapshot with limit=10: {len(snap.elements)} elements")


async def actions_example():
    """Example of all async actions"""
    async with AsyncSentienceBrowser(headless=False) as browser:
        await browser.goto("https://example.com")

        # Take snapshot
        snap = await snapshot_async(browser)

        # Find a textbox if available
        textbox = find(snap, "role=textbox")
        if textbox:
            # Type text (async)
            result = await type_text_async(browser, textbox.id, "Hello, World!")
            print(f"✅ Typed text: success={result.success}")

        # Press a key (async)
        result = await press_async(browser, "Enter")
        print(f"✅ Pressed Enter: success={result.success}")


async def from_existing_context_example():
    """Example using from_existing() with existing Playwright context"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # Create your own Playwright context
        context = await p.chromium.launch_persistent_context("", headless=True)

        try:
            # Create SentienceBrowser from existing context
            browser = await AsyncSentienceBrowser.from_existing(context)
            await browser.goto("https://example.com")

            # Use Sentience SDK functions
            snap = await snapshot_async(browser)
            print(f"✅ Using existing context: {len(snap.elements)} elements")
        finally:
            await context.close()


async def from_existing_page_example():
    """Example using from_page() with existing Playwright page"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser_instance = await p.chromium.launch(headless=True)
        context = await browser_instance.new_context()
        page = await context.new_page()

        try:
            # Create SentienceBrowser from existing page
            sentience_browser = await AsyncSentienceBrowser.from_page(page)
            await sentience_browser.goto("https://example.com")

            # Use Sentience SDK functions
            snap = await snapshot_async(sentience_browser)
            print(f"✅ Using existing page: {len(snap.elements)} elements")
        finally:
            await context.close()
            await browser_instance.close()


async def multiple_browsers_example():
    """Example running multiple browsers concurrently"""

    async def process_site(url: str):
        async with AsyncSentienceBrowser(headless=True) as browser:
            await browser.goto(url)
            snap = await snapshot_async(browser)
            return {"url": url, "elements": len(snap.elements)}

    # Process multiple sites concurrently
    urls = [
        "https://example.com",
        "https://httpbin.org/html",
    ]

    results = await asyncio.gather(*[process_site(url) for url in urls])
    for result in results:
        print(f"✅ {result['url']}: {result['elements']} elements")


async def main():
    """Run all examples"""
    print("=== Basic Async Example ===")
    await basic_async_example()

    print("\n=== Custom Viewport Example ===")
    await custom_viewport_example()

    print("\n=== Snapshot with Options Example ===")
    await snapshot_with_options_example()

    print("\n=== Actions Example ===")
    await actions_example()

    print("\n=== From Existing Context Example ===")
    await from_existing_context_example()

    print("\n=== From Existing Page Example ===")
    await from_existing_page_example()

    print("\n=== Multiple Browsers Concurrent Example ===")
    await multiple_browsers_example()

    print("\n✅ All async examples completed!")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
