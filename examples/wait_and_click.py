"""
Example: Wait for element and click
"""

import os

from sentience import SentienceBrowser, click, expect, find, snapshot, wait_for


def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    with SentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to example.com
        browser.page.goto("https://example.com", wait_until="domcontentloaded")

        # Take initial snapshot
        snap = snapshot(browser)

        # Find a link
        link = find(snap, "role=link")

        if link:
            print(f"Found link: {link.text} (id: {link.id})")

            # Click it
            result = click(browser, link.id)
            print(f"Click result: success={result.success}, outcome={result.outcome}")

            print(f"New URL: {browser.page.url}")
        else:
            print("No link found")

        # Example: Wait for element using wait_for
        print("\n=== Wait Example ===")
        browser.page.goto("https://example.com", wait_until="domcontentloaded")

        wait_result = wait_for(browser, "role=link", timeout=5.0)
        if wait_result.found:
            print(f"✅ Found element after {wait_result.duration_ms}ms")
        else:
            print(f"❌ Element not found (timeout: {wait_result.timeout})")

        # Example: Expect assertion
        print("\n=== Expect Example ===")
        try:
            element = expect(browser, "role=link").to_exist(timeout=5.0)
            print(f"✅ Element exists: {element.text}")
        except AssertionError as e:
            print(f"❌ Assertion failed: {e}")


if __name__ == "__main__":
    main()
