"""
Text Search Demo - Using find_text_rect() to locate elements by visible text

This example demonstrates how to:
1. Find text on a webpage and get exact pixel coordinates
2. Use case-sensitive and whole-word matching options
3. Click on found text using click_rect()
4. Handle multiple matches and filter by viewport visibility
"""

from predicate import SentienceBrowser, click_rect, find_text_rect


def main():
    with SentienceBrowser() as browser:
        # Navigate to a search page
        browser.page.goto("https://www.google.com")
        browser.page.wait_for_load_state("networkidle")

        print("\n" + "=" * 60)
        print("Text Search Demo")
        print("=" * 60 + "\n")

        # Example 1: Simple text search
        print("Example 1: Finding 'Google Search' button")
        print("-" * 60)
        result = find_text_rect(browser, "Google Search")

        if result.status == "success" and result.results:
            print(f"✓ Found {result.matches} match(es) for '{result.query}'")
            for i, match in enumerate(result.results[:3]):  # Show first 3
                print(f"\nMatch {i + 1}:")
                print(f"  Text: '{match.text}'")
                print(f"  Position: ({match.rect.x:.1f}, {match.rect.y:.1f})")
                print(f"  Size: {match.rect.width:.1f}x{match.rect.height:.1f} pixels")
                print(f"  In viewport: {match.in_viewport}")
                print(f"  Context: ...{match.context.before}[{match.text}]{match.context.after}...")
        else:
            print(f"✗ Search failed: {result.error}")

        # Example 2: Find and click search box
        print("\n\nExample 2: Finding and clicking the search box")
        print("-" * 60)
        result = find_text_rect(browser, "Search", max_results=5)

        if result.status == "success" and result.results:
            # Find the first visible match
            for match in result.results:
                if match.in_viewport:
                    print(f"✓ Found visible match: '{match.text}'")
                    print(f"  Clicking at ({match.rect.x:.1f}, {match.rect.y:.1f})")

                    # Click in the center of the text
                    click_result = click_rect(
                        browser,
                        {
                            "x": match.rect.x,
                            "y": match.rect.y,
                            "w": match.rect.width,
                            "h": match.rect.height,
                        },
                    )

                    if click_result.success:
                        print(f"  ✓ Click successful!")
                    break

        # Example 3: Case-sensitive search
        print("\n\nExample 3: Case-sensitive search for 'GOOGLE'")
        print("-" * 60)
        result_insensitive = find_text_rect(browser, "GOOGLE", case_sensitive=False)
        result_sensitive = find_text_rect(browser, "GOOGLE", case_sensitive=True)

        print(f"Case-insensitive search: {result_insensitive.matches or 0} matches")
        print(f"Case-sensitive search: {result_sensitive.matches or 0} matches")

        # Example 4: Whole word search
        print("\n\nExample 4: Whole word search")
        print("-" * 60)
        result_partial = find_text_rect(browser, "Search", whole_word=False)
        result_whole = find_text_rect(browser, "Search", whole_word=True)

        print(f"Partial word match: {result_partial.matches or 0} matches")
        print(f"Whole word only: {result_whole.matches or 0} matches")

        # Example 5: Get viewport information
        print("\n\nExample 5: Viewport and scroll information")
        print("-" * 60)
        result = find_text_rect(browser, "Google")
        if result.status == "success" and result.viewport:
            print(f"Viewport size: {result.viewport.width}x{result.viewport.height}")
            # Note: scroll position would be available if viewport had scroll_x/scroll_y fields

        print("\n" + "=" * 60)
        print("Demo complete!")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
