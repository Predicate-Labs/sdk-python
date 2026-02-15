"""
Example: Using Sentience with browser-use for element grounding.

This example demonstrates how to integrate Sentience's semantic element
detection with browser-use, enabling accurate click/type/scroll operations
using Sentience's snapshot-based grounding instead of coordinate estimation.

Requirements:
    pip install "predicate-sdk[browser-use]" python-dotenv

    Or install separately:
    pip install predicate-sdk browser-use python-dotenv

Usage:
    python examples/browser-use/integration.py
"""

import asyncio
import glob
from pathlib import Path

from dotenv import load_dotenv

# Sentience imports
from predicate import find, get_extension_dir, query
from predicate.backends import (
    BrowserUseAdapter,
    CachedSnapshot,
    ExtensionNotLoadedError,
    SentienceContext,
    TopElementSelector,
    click,
    scroll,
    snapshot,
    type_text,
)

# browser-use imports (install via: pip install browser-use)
# Uncomment these when running with browser-use installed:
# from browser_use import Agent, BrowserProfile, BrowserSession, ChatBrowserUse

load_dotenv()


def find_playwright_browser() -> str | None:
    """Find Playwright browser executable to avoid password prompt."""
    playwright_path = Path.home() / "Library/Caches/ms-playwright"
    chromium_patterns = [
        playwright_path
        / "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        playwright_path / "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    ]

    for pattern in chromium_patterns:
        matches = glob.glob(str(pattern))
        if matches:
            matches.sort()
            executable_path = matches[-1]  # Use latest version
            if Path(executable_path).exists():
                print(f"Found Playwright browser: {executable_path}")
                return executable_path

    print("Playwright browser not found, browser-use will try to install it")
    return None


def get_browser_profile_with_sentience():
    """
    Create a BrowserProfile with Sentience extension loaded.

    Chrome only uses the LAST --load-extension arg, so we must combine
    all extensions (Sentience + defaults) into a single argument.
    """
    # Uncomment when running with browser-use installed:
    # from browser_use import BrowserProfile

    # Get Sentience extension path
    sentience_ext_path = get_extension_dir()
    print(f"Loading Sentience extension from: {sentience_ext_path}")

    # Get default extension paths and combine with Sentience extension
    all_extension_paths = [sentience_ext_path]

    # Create a temporary profile to ensure default extensions are downloaded
    # Uncomment when running with browser-use installed:
    # temp_profile = BrowserProfile(enable_default_extensions=True)
    # default_ext_paths = temp_profile._ensure_default_extensions_downloaded()
    #
    # if default_ext_paths:
    #     all_extension_paths.extend(default_ext_paths)
    #     print(f"Found {len(default_ext_paths)} default extensions")

    # Combine all extensions into a single --load-extension arg
    combined_extensions = ",".join(all_extension_paths)
    print(f"Loading {len(all_extension_paths)} extensions total (including Sentience)")

    # Uncomment when running with browser-use installed:
    # executable_path = find_playwright_browser()
    #
    # return BrowserProfile(
    #     executable_path=executable_path,
    #     enable_default_extensions=False,  # We load manually
    #     args=[
    #         "--enable-extensions",
    #         "--disable-extensions-file-access-check",
    #         "--disable-extensions-http-throttling",
    #         "--extensions-on-chrome-urls",
    #         f"--load-extension={combined_extensions}",
    #     ],
    # )

    return None  # Placeholder


async def example_with_sentience_context() -> None:
    """
    Example using SentienceContext for token-slashed DOM context.

    SentienceContext provides a compact, ranked DOM context block that
    reduces tokens by ~80% compared to raw DOM dumps while improving
    element selection accuracy.
    """
    # Uncomment when running with browser-use installed:
    # from browser_use import Agent, BrowserSession, ChatBrowserUse

    print("=" * 60)
    print("SentienceContext Integration Example")
    print("=" * 60)

    # =========================================================================
    # STEP 1: Setup browser-use with Sentience extension
    # =========================================================================

    # browser_profile = get_browser_profile_with_sentience()
    # session = BrowserSession(browser_profile=browser_profile)
    # await session.start()

    # =========================================================================
    # STEP 2: Create SentienceContext
    # =========================================================================
    #
    # SentienceContext provides a clean API for getting compact DOM context:
    #
    #   - sentience_api_key: Optional API key for gateway mode
    #   - max_elements: Maximum elements to fetch (default: 60)
    #   - show_overlay: Show visual overlay on elements (default: False)
    #   - top_element_selector: Configure element selection strategy

    ctx = SentienceContext(
        max_elements=60,
        show_overlay=False,
        top_element_selector=TopElementSelector(
            by_importance=60,  # Top N by importance score
            from_dominant_group=15,  # Top N from dominant group (for ordinal tasks)
            by_position=10,  # Top N by position (top of page)
        ),
    )

    # =========================================================================
    # STEP 3: Build context from browser session
    # =========================================================================
    #
    # The build() method:
    #   1. Waits for Sentience extension to load (configurable timeout)
    #   2. Takes a snapshot using the extension
    #   3. Formats elements into a compact prompt block
    #
    # await session.navigate("https://news.ycombinator.com")
    #
    # state = await ctx.build(
    #     session,
    #     goal="Find the first Show HN post",  # Optional: helps with reranking
    #     wait_for_extension_ms=5000,          # Wait up to 5s for extension
    #     retries=2,                           # Retry on failure
    # )
    #
    # if state:
    #     print(f"URL: {state.url}")
    #     print(f"Elements: {len(state.snapshot.elements)}")
    #     print(f"Prompt block preview:\n{state.prompt_block[:500]}...")

    # =========================================================================
    # STEP 4: Using the prompt block with an LLM agent
    # =========================================================================
    #
    # The prompt_block contains:
    #   - Header: "Elements: ID|role|text|imp|is_primary|docYq|ord|DG|href"
    #   - Rules for interpreting the data
    #   - Compact element list
    #
    # You can inject this into your agent's context:
    #
    # llm = ChatBrowserUse()
    # agent = Agent(
    #     task="Click the first Show HN post",
    #     llm=llm,
    #     browser_profile=browser_profile,
    #     use_vision=False,  # Sentience provides semantic geometry
    # )
    #
    # # Inject Sentience context into the agent (method depends on browser-use API)
    # agent.add_context(state.prompt_block)

    # =========================================================================
    # STEP 5: Direct element interaction (alternative to agent)
    # =========================================================================
    #
    # You can also use Sentience's direct action APIs:
    #
    # adapter = BrowserUseAdapter(session)
    # backend = await adapter.create_backend()
    #
    # # Take snapshot
    # snap = await snapshot(backend)
    #
    # # Find element by semantic query
    # show_hn_link = find(snap, 'role=link[name*="Show HN"]')
    # if show_hn_link:
    #     await click(backend, show_hn_link.bbox)
    #
    # # Type into an input
    # search_box = find(snap, 'role=textbox')
    # if search_box:
    #     await click(backend, search_box.bbox)
    #     await type_text(backend, "Sentience AI")

    # =========================================================================
    # Print example info
    # =========================================================================

    print()
    print("SentienceContext Configuration:")
    print(f"  max_elements: {ctx._max_elements}")
    print(f"  show_overlay: {ctx._show_overlay}")
    print(f"  top_element_selector:")
    print(f"    by_importance: {ctx._selector.by_importance}")
    print(f"    from_dominant_group: {ctx._selector.from_dominant_group}")
    print(f"    by_position: {ctx._selector.by_position}")
    print()
    print("Extension path:", get_extension_dir())
    print()
    print("To run with a real browser:")
    print('  1. pip install "predicate-sdk[browser-use]" python-dotenv')
    print("  2. Uncomment the browser-use imports and code sections")
    print("  3. Run: python examples/browser-use/integration.py")


async def example_low_level_api() -> None:
    """
    Example using low-level Sentience APIs for fine-grained control.

    Use this approach when you need direct control over snapshots
    and element interactions, rather than the higher-level SentienceContext.
    """
    print("=" * 60)
    print("Low-Level Sentience API Example")
    print("=" * 60)

    # =========================================================================
    # Direct snapshot and interaction pattern
    # =========================================================================
    #
    # from browser_use import BrowserSession, BrowserProfile
    #
    # browser_profile = get_browser_profile_with_sentience()
    # session = BrowserSession(browser_profile=browser_profile)
    # await session.start()
    #
    # # Create adapter and backend
    # adapter = BrowserUseAdapter(session)
    # backend = await adapter.create_backend()
    #
    # await session.navigate("https://www.google.com")
    #
    # # Take snapshot with retry
    # try:
    #     snap = await snapshot(backend)
    #     print(f"Found {len(snap.elements)} elements")
    # except ExtensionNotLoadedError as e:
    #     print(f"Extension not loaded: {e}")
    #     return

    # =========================================================================
    # Element queries
    # =========================================================================
    #
    # # Find single element
    # search_input = find(snap, 'role=textbox[name*="Search"]')
    #
    # # Find all matching elements
    # all_links = query(snap, 'role=link')
    # print(f"Found {len(all_links)} links")
    #
    # # Click and type
    # if search_input:
    #     await click(backend, search_input.bbox)
    #     await type_text(backend, "Sentience AI browser automation")

    # =========================================================================
    # Cached snapshots for efficiency
    # =========================================================================
    #
    # cache = CachedSnapshot(backend, max_age_ms=2000)
    #
    # snap1 = await cache.get()  # Fresh snapshot
    # snap2 = await cache.get()  # Returns cached if < 2s old
    #
    # await click(backend, some_element.bbox)
    # cache.invalidate()  # Force refresh on next get()

    # =========================================================================
    # Scrolling
    # =========================================================================
    #
    # await scroll(backend, delta_y=500)  # Scroll down
    # await scroll(backend, delta_y=-300)  # Scroll up
    # await scroll(backend, delta_y=300, target=(400, 500))  # At position

    print()
    print("Low-level APIs available:")
    print("  - snapshot(backend) -> Snapshot")
    print("  - find(snap, selector) -> Element | None")
    print("  - query(snap, selector) -> list[Element]")
    print("  - click(backend, bbox)")
    print("  - type_text(backend, text)")
    print("  - scroll(backend, delta_y, target)")
    print("  - CachedSnapshot(backend, max_age_ms)")


async def main() -> None:
    """Run all examples."""
    await example_with_sentience_context()
    print()
    await example_low_level_api()


if __name__ == "__main__":
    asyncio.run(main())
