"""
Example: Basic snapshot functionality
"""

from sentience import SentienceBrowser, snapshot
import os


def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    with SentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to a test page
        browser.page.goto("https://example.com", wait_until="domcontentloaded")
        
        # Take snapshot
        snap = snapshot(browser)
        
        print(f"Status: {snap.status}")
        print(f"URL: {snap.url}")
        print(f"Elements found: {len(snap.elements)}")
        
        # Show top 5 elements
        print("\nTop 5 elements:")
        for i, el in enumerate(snap.elements[:5], 1):
            print(f"{i}. [{el.role}] {el.text or '(no text)'} (importance: {el.importance})")
        
        # Save snapshot
        snap.save("snapshot_example.json")
        print("\n✅ Snapshot saved to snapshot_example.json")


if __name__ == "__main__":
    main()

