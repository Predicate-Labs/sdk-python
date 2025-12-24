"""
Example: Using click_rect for coordinate-based clicking with visual feedback
"""

import os

from sentience import SentienceBrowser, click_rect, find, snapshot


def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    with SentienceBrowser(api_key=api_key, headless=False) as browser:
        # Navigate to example.com
        browser.page.goto("https://example.com", wait_until="domcontentloaded")

        print("=== click_rect Demo ===\n")

        # Example 1: Click using rect dictionary
        print("1. Clicking at specific coordinates (100, 100) with size 50x30")
        print("   (You should see a red border highlight for 2 seconds)")
        result = click_rect(browser, {"x": 100, "y": 100, "w": 50, "h": 30})
        print(f"   Result: success={result.success}, outcome={result.outcome}")
        print(f"   Duration: {result.duration_ms}ms\n")

        # Wait a bit
        browser.page.wait_for_timeout(1000)

        # Example 2: Click using element's bbox
        print("2. Clicking using element's bounding box")
        snap = snapshot(browser)
        link = find(snap, "role=link")

        if link:
            print(f"   Found link: '{link.text}' at ({link.bbox.x}, {link.bbox.y})")
            print("   Clicking at center of element's bbox...")
            result = click_rect(
                browser,
                {"x": link.bbox.x, "y": link.bbox.y, "w": link.bbox.width, "h": link.bbox.height},
            )
            print(f"   Result: success={result.success}, outcome={result.outcome}")
            print(f"   URL changed: {result.url_changed}\n")

            # Navigate back if needed
            if result.url_changed:
                browser.page.goto("https://example.com", wait_until="domcontentloaded")
                browser.page.wait_for_load_state("networkidle")

        # Example 3: Click without highlight (for headless/CI)
        print("3. Clicking without visual highlight")
        result = click_rect(browser, {"x": 200, "y": 200, "w": 40, "h": 20}, highlight=False)
        print(f"   Result: success={result.success}\n")

        # Example 4: Custom highlight duration
        print("4. Clicking with custom highlight duration (3 seconds)")
        result = click_rect(browser, {"x": 300, "y": 300, "w": 60, "h": 40}, highlight_duration=3.0)
        print(f"   Result: success={result.success}")
        print("   (Red border should stay visible for 3 seconds)\n")

        # Example 5: Click with snapshot capture
        print("5. Clicking and capturing snapshot after action")
        result = click_rect(browser, {"x": 150, "y": 150, "w": 50, "h": 30}, take_snapshot=True)
        if result.snapshot_after:
            print(f"   Snapshot captured: {len(result.snapshot_after.elements)} elements found")
            print(f"   URL: {result.snapshot_after.url}\n")

        print("✅ click_rect demo complete!")
        print("\nNote: click_rect uses Playwright's native mouse.click() for realistic")
        print("event simulation, triggering hover, focus, mousedown, mouseup sequences.")


if __name__ == "__main__":
    main()
