"""
Example: Verify extension bridge is loaded (Async version)
"""

import asyncio
import os

from sentience.async_api import AsyncSentienceBrowser


async def main():
    # Get API key from environment variable (optional - uses free tier if not set)
    api_key = os.environ.get("SENTIENCE_API_KEY")

    try:
        async with AsyncSentienceBrowser(api_key=api_key, headless=False) as browser:
            # Navigate to a page to ensure extension is active
            await browser.goto("https://example.com", wait_until="domcontentloaded")

            # Check if extension API is available
            bridge_ok = await browser.page.evaluate(
                """
                () => {
                    return typeof window.sentience !== 'undefined' &&
                           typeof window.sentience.snapshot === 'function';
                }
            """
            )
            print(f"bridge_ok={bridge_ok}")

            if bridge_ok:
                print("✅ Extension loaded successfully!")
                # Try a quick snapshot to verify it works
                try:
                    result = await browser.page.evaluate("window.sentience.snapshot({ limit: 1 })")
                    if result.get("status") == "success":
                        print(f"✅ Snapshot test: Found {len(result.get('elements', []))} elements")
                    else:
                        print(f"⚠️  Snapshot returned: {result.get('status')}")
                except Exception as e:
                    print(f"⚠️  Snapshot test failed: {e}")
            else:
                print("❌ Extension not loaded")
                # Debug info
                debug_info = await browser.page.evaluate(
                    """
                    () => {
                        return {
                            sentience_defined: typeof window.sentience !== 'undefined',
                            registry_defined: typeof window.sentience_registry !== 'undefined',
                            snapshot_defined: typeof window.sentience?.snapshot !== 'undefined'
                        };
                    }
                """
                )
                print(f"Debug info: {debug_info}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
