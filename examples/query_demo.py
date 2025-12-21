"""
Day 4 Example: Query engine demonstration
"""

from sentience import SentienceBrowser, snapshot, query, find


def main():
    with SentienceBrowser(headless=False) as browser:
        # Navigate to a page with links
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
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

