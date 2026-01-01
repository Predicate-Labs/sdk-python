"""
Example: Semantic wait_for using query DSL (Async version)
Demonstrates waiting for elements using semantic selectors
"""

import asyncio
import os

from sentience.async_api import AsyncSentienceBrowser, click_async, wait_for_async


async def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to example.com
        await browser.goto("https://example.com", wait_until="domcontentloaded")

        print("=== Semantic wait_for_async Demo ===\n")

        # Example 1: Wait for element by role
        print("1. Waiting for link element (role=link)")
        wait_result = await wait_for_async(browser, "role=link", timeout=5.0)
        if wait_result.found:
            print(f"   ✅ Found after {wait_result.duration_ms}ms")
            print(f"   Element: '{wait_result.element.text}' (id: {wait_result.element.id})")
        else:
            print(f"   ❌ Not found (timeout: {wait_result.timeout})")
        print()

        # Example 2: Wait for element by role and text
        print("2. Waiting for link with specific text")
        wait_result = await wait_for_async(browser, "role=link text~'Example'", timeout=5.0)
        if wait_result.found:
            print(f"   ✅ Found after {wait_result.duration_ms}ms")
            print(f"   Element text: '{wait_result.element.text}'")
        else:
            print("   ❌ Not found")
        print()

        # Example 3: Wait for clickable element
        print("3. Waiting for clickable element")
        wait_result = await wait_for_async(browser, "clickable=true", timeout=5.0)
        if wait_result.found:
            print(f"   ✅ Found clickable element after {wait_result.duration_ms}ms")
            print(f"   Role: {wait_result.element.role}")
            print(f"   Text: '{wait_result.element.text}'")
            print(f"   Is clickable: {wait_result.element.visual_cues.is_clickable}")
        else:
            print("   ❌ Not found")
        print()

        # Example 4: Wait for element with importance threshold
        print("4. Waiting for important element (importance > 100)")
        wait_result = await wait_for_async(browser, "importance>100", timeout=5.0)
        if wait_result.found:
            print(f"   ✅ Found important element after {wait_result.duration_ms}ms")
            print(f"   Importance: {wait_result.element.importance}")
            print(f"   Role: {wait_result.element.role}")
        else:
            print("   ❌ Not found")
        print()

        # Example 5: Wait and then click
        print("5. Wait for element, then click it")
        wait_result = await wait_for_async(browser, "role=link", timeout=5.0)
        if wait_result.found:
            print("   ✅ Found element, clicking...")
            click_result = await click_async(browser, wait_result.element.id)
            print(
                f"   Click result: success={click_result.success}, outcome={click_result.outcome}"
            )
            if click_result.url_changed:
                print(f"   ✅ Navigation occurred: {browser.page.url}")
        else:
            print("   ❌ Element not found, cannot click")
        print()

        # Example 6: Using local extension (fast polling)
        print("6. Using local extension with auto-optimized interval")
        print("   When use_api=False, interval auto-adjusts to 0.25s (fast)")
        wait_result = await wait_for_async(browser, "role=link", timeout=5.0, use_api=False)
        if wait_result.found:
            print(f"   ✅ Found after {wait_result.duration_ms}ms")
            print("   (Used local extension, polled every 0.25 seconds)")
        print()

        # Example 7: Using remote API (slower polling)
        print("7. Using remote API with auto-optimized interval")
        print("   When use_api=True, interval auto-adjusts to 1.5s (network-friendly)")
        if api_key:
            wait_result = await wait_for_async(browser, "role=link", timeout=5.0, use_api=True)
            if wait_result.found:
                print(f"   ✅ Found after {wait_result.duration_ms}ms")
                print("   (Used remote API, polled every 1.5 seconds)")
        else:
            print("   ⚠️  Skipped (no API key set)")
        print()

        # Example 8: Custom interval override
        print("8. Custom interval override (manual control)")
        print("   You can still specify custom interval if needed")
        wait_result = await wait_for_async(
            browser, "role=link", timeout=5.0, interval=0.5, use_api=False
        )
        if wait_result.found:
            print(f"   ✅ Found after {wait_result.duration_ms}ms")
            print("   (Custom interval: 0.5 seconds)")
        print()

        print("✅ Semantic wait_for_async demo complete!")
        print("\nNote: wait_for_async uses the semantic query DSL to find elements.")
        print("This is more robust than CSS selectors because it understands")
        print("the semantic meaning of elements (role, text, clickability, etc.).")


if __name__ == "__main__":
    asyncio.run(main())

