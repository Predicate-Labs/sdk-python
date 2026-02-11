"""
Example: Query engine demonstration (Async version)
"""

import asyncio
import os

from predicate.async_api import AsyncSentienceBrowser, find, query, snapshot_async


async def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to a page with links
        await browser.goto("https://example.com", wait_until="domcontentloaded")

        snap = await snapshot_async(browser)

        # Query examples
        print("=== Query Examples ===\n")

        # Find all buttons
        buttons = query(snap, "role=button")
        print(f"Found {len(buttons)} buttons")

        # Find all links
        links = query(snap, "role=link")
        print(f"Found {len(links)} links")

        # Find clickable elements
        clickables = query(snap, "clickable=true")
        print(f"Found {len(clickables)} clickable elements")

        # Find element with text containing "More"
        more_link = find(snap, "text~'More'")
        if more_link:
            print(f"\nFound 'More' link: {more_link.text} (id: {more_link.id})")
        else:
            print("\nNo 'More' link found")

        # Complex query: clickable links
        clickable_links = query(snap, "role=link clickable=true")
        print(f"\nFound {len(clickable_links)} clickable links")


if __name__ == "__main__":
    asyncio.run(main())
