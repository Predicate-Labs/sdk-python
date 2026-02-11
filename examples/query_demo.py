"""
Example: Query engine demonstration
"""

import os

from predicate import SentienceBrowser, find, query, snapshot


def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    with SentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to a page with links
        browser.page.goto("https://example.com", wait_until="domcontentloaded")

        snap = snapshot(browser)

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
    main()
