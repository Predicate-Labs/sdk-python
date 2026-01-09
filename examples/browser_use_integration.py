"""
Example: Using Sentience with browser-use for element grounding.

This example demonstrates how to integrate Sentience's semantic element
detection with browser-use, enabling accurate click/type/scroll operations
using Sentience's snapshot-based grounding instead of coordinate estimation.

Requirements:
    pip install browser-use sentienceapi

Usage:
    python examples/browser_use_integration.py
"""

import asyncio

# Sentience imports
from sentience import find, get_extension_dir, query
from sentience.backends import (
    BrowserUseAdapter,
    CachedSnapshot,
    ExtensionNotLoadedError,
    click,
    scroll,
    snapshot,
    type_text,
)

# browser-use imports (install via: pip install browser-use)
# from browser_use import BrowserSession, BrowserProfile


async def main() -> None:
    """
    Demo: Search on Google using Sentience grounding with browser-use.

    This example shows the full workflow:
    1. Launch browser-use with Sentience extension loaded
    2. Create a Sentience backend adapter
    3. Take snapshots and interact with elements using semantic queries
    """

    # =========================================================================
    # STEP 1: Setup browser-use with Sentience extension
    # =========================================================================
    #
    # The Sentience extension must be loaded for element grounding to work.
    # Use get_extension_dir() to get the path to the bundled extension.
    #
    # Uncomment the following when running with browser-use installed:

    # extension_path = get_extension_dir()
    # print(f"Loading Sentience extension from: {extension_path}")
    #
    # profile = BrowserProfile(
    #     args=[
    #         f"--load-extension={extension_path}",
    #         "--disable-extensions-except=" + extension_path,
    #     ],
    # )
    # session = BrowserSession(browser_profile=profile)
    # await session.start()

    # =========================================================================
    # STEP 2: Create Sentience backend adapter
    # =========================================================================
    #
    # The adapter bridges browser-use's CDP client to Sentience's backend protocol.
    #
    # adapter = BrowserUseAdapter(session)
    # backend = await adapter.create_backend()

    # =========================================================================
    # STEP 3: Navigate and take snapshots
    # =========================================================================
    #
    # await session.navigate("https://www.google.com")
    #
    # # Take a snapshot - this uses the Sentience extension's element detection
    # try:
    #     snap = await snapshot(backend)
    #     print(f"Found {len(snap.elements)} elements")
    # except ExtensionNotLoadedError as e:
    #     print(f"Extension not loaded: {e}")
    #     print("Make sure the browser was launched with --load-extension flag")
    #     return

    # =========================================================================
    # STEP 4: Find and interact with elements using semantic queries
    # =========================================================================
    #
    # Sentience provides powerful element selectors:
    # - Role-based: 'role=textbox', 'role=button'
    # - Name-based: 'role=button[name="Submit"]'
    # - Text-based: 'text=Search'
    #
    # # Find the search input
    # search_input = find(snap, 'role=textbox[name*="Search"]')
    # if search_input:
    #     # Click on the search input (uses center of bounding box)
    #     await click(backend, search_input.bbox)
    #
    #     # Type search query
    #     await type_text(backend, "Sentience AI browser automation")
    #     print("Typed search query")

    # =========================================================================
    # STEP 5: Using cached snapshots for efficiency
    # =========================================================================
    #
    # Taking snapshots has overhead. Use CachedSnapshot to reuse recent snapshots:
    #
    # cache = CachedSnapshot(backend, max_age_ms=2000)
    #
    # # First call takes fresh snapshot
    # snap1 = await cache.get()
    #
    # # Second call returns cached version if less than 2 seconds old
    # snap2 = await cache.get()
    #
    # # After actions that modify DOM, invalidate the cache
    # await click(backend, some_element.bbox)
    # cache.invalidate()  # Next get() will take fresh snapshot

    # =========================================================================
    # STEP 6: Scrolling to elements
    # =========================================================================
    #
    # # Scroll down by 500 pixels
    # await scroll(backend, delta_y=500)
    #
    # # Scroll at a specific position (useful for scrollable containers)
    # await scroll(backend, delta_y=300, target=(400, 500))

    # =========================================================================
    # STEP 7: Advanced element queries
    # =========================================================================
    #
    # # Find all buttons
    # buttons = query(snap, 'role=button')
    # print(f"Found {len(buttons)} buttons")
    #
    # # Find by partial text match
    # links = query(snap, 'role=link[name*="Learn"]')
    #
    # # Find by exact text
    # submit_btn = find(snap, 'role=button[name="Submit"]')

    # =========================================================================
    # STEP 8: Error handling
    # =========================================================================
    #
    # Sentience provides specific exceptions for common errors:
    #
    # from sentience.backends import (
    #     ExtensionNotLoadedError,  # Extension not loaded in browser
    #     SnapshotError,            # Snapshot failed
    #     ActionError,              # Click/type/scroll failed
    # )
    #
    # try:
    #     snap = await snapshot(backend)
    # except ExtensionNotLoadedError as e:
    #     # The error message includes fix suggestions
    #     print(f"Fix: {e}")

    # =========================================================================
    # CLEANUP
    # =========================================================================
    #
    # await session.stop()

    print("=" * 60)
    print("browser-use + Sentience Integration Example")
    print("=" * 60)
    print()
    print("This example demonstrates the integration pattern.")
    print("To run with a real browser, uncomment the code sections above")
    print("and install browser-use: pip install browser-use")
    print()
    print("Key imports:")
    print("  from sentience import get_extension_dir, find, query")
    print("  from sentience.backends import (")
    print("      BrowserUseAdapter, snapshot, click, type_text, scroll")
    print("  )")
    print()
    print("Extension path:", get_extension_dir())


async def full_example() -> None:
    """
    Complete working example - requires browser-use installed.

    This is the uncommented version for users who have browser-use installed.
    """
    # Import browser-use (uncomment when installed)
    # from browser_use import BrowserSession, BrowserProfile

    print("To run the full example:")
    print("1. Install browser-use: pip install browser-use")
    print("2. Uncomment the imports in this function")
    print("3. Run: python examples/browser_use_integration.py")


if __name__ == "__main__":
    asyncio.run(main())
