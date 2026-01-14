"""
Example: Grid Overlay Visualization

Demonstrates how to use the grid overlay feature to visualize detected grids
on a webpage, including highlighting specific grids and identifying the dominant group.
"""

import os
import time

from sentience import SentienceBrowser, snapshot
from sentience.models import SnapshotOptions


def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")
    
    # Use VPS IP directly if domain is not configured
    # Replace with your actual domain once DNS is set up: api_url="https://api.sentienceapi.com"
    api_url = os.environ.get("SENTIENCE_API_URL", "http://15.204.243.91:9000")

    try:
        with SentienceBrowser(api_key=api_key, api_url=api_url, headless=False) as browser:
            # Navigate to a page with grid layouts (e.g., product listings, article feeds)
            browser.page.goto("https://example.com", wait_until="domcontentloaded")
            time.sleep(2)  # Wait for page to fully load

            print("=" * 60)
            print("Example 1: Show all detected grids")
            print("=" * 60)
            # Show all grids (all in purple)
            snap = snapshot(browser, SnapshotOptions(show_grid=True, use_api=True))
            print(f"✅ Found {len(snap.elements)} elements")
            print("   Purple borders appear around all detected grids for 5 seconds")
            time.sleep(6)  # Wait to see the overlay

            print("\n" + "=" * 60)
            print("Example 2: Highlight a specific grid in red")
            print("=" * 60)
            # Get grid information first
            grids = snap.get_grid_bounds()
            if grids:
                print(f"✅ Found {len(grids)} grids:")
                for grid in grids:
                    print(f"   Grid {grid.grid_id}: {grid.item_count} items, "
                          f"{grid.row_count}x{grid.col_count} rows/cols, "
                          f"label: {grid.label or 'none'}")
                
                # Highlight the first grid in red
                if len(grids) > 0:
                    target_grid_id = grids[0].grid_id
                    print(f"\n   Highlighting Grid {target_grid_id} in red...")
                    snap = snapshot(browser, SnapshotOptions(
                        show_grid=True,
                        grid_id=target_grid_id  # This grid will be highlighted in red
                    ))
                    time.sleep(6)  # Wait to see the overlay
            else:
                print("   ⚠️  No grids detected on this page")

            print("\n" + "=" * 60)
            print("Example 3: Highlight the dominant group")
            print("=" * 60)
            # Find and highlight the dominant grid
            grids = snap.get_grid_bounds()
            dominant_grid = next((g for g in grids if g.is_dominant), None)
            
            if dominant_grid:
                print(f"✅ Dominant group detected: Grid {dominant_grid.grid_id}")
                print(f"   Label: {dominant_grid.label or 'none'}")
                print(f"   Items: {dominant_grid.item_count}")
                print(f"   Size: {dominant_grid.row_count}x{dominant_grid.col_count}")
                print(f"\n   Highlighting dominant grid in red...")
                snap = snapshot(browser, SnapshotOptions(
                    show_grid=True,
                    grid_id=dominant_grid.grid_id  # Highlight dominant grid in red
                ))
                time.sleep(6)  # Wait to see the overlay
            else:
                print("   ⚠️  No dominant group detected")

            print("\n" + "=" * 60)
            print("Example 4: Combine element overlay and grid overlay")
            print("=" * 60)
            # Show both element borders and grid borders simultaneously
            snap = snapshot(browser, SnapshotOptions(
                show_overlay=True,  # Show element borders (green/blue/red)
                show_grid=True      # Show grid borders (purple/orange/red)
            ))
            print("✅ Both overlays are now visible:")
            print("   - Element borders: Green (regular), Blue (primary), Red (target)")
            print("   - Grid borders: Purple (regular), Orange (dominant), Red (target)")
            time.sleep(6)  # Wait to see the overlay

            print("\n" + "=" * 60)
            print("Example 5: Grid information analysis")
            print("=" * 60)
            # Analyze grid structure
            grids = snap.get_grid_bounds()
            print(f"✅ Grid Analysis:")
            for grid in grids:
                dominant_indicator = "⭐ DOMINANT" if grid.is_dominant else ""
                print(f"\n   Grid {grid.grid_id} {dominant_indicator}:")
                print(f"      Label: {grid.label or 'none'}")
                print(f"      Items: {grid.item_count}")
                print(f"      Size: {grid.row_count} rows × {grid.col_count} cols")
                print(f"      BBox: ({grid.bbox.x:.0f}, {grid.bbox.y:.0f}) "
                      f"{grid.bbox.width:.0f}×{grid.bbox.height:.0f}")
                print(f"      Confidence: {grid.confidence}")

            print("\n✅ All examples completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
