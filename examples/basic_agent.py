"""
Day 3 Example: Basic snapshot functionality
"""

from sentience import SentienceBrowser, snapshot


def main():
    with SentienceBrowser(headless=False) as browser:
        # Navigate to a test page
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
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

