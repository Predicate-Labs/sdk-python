"""
Day 2 Example: Verify extension bridge is loaded
"""

from sentience import SentienceBrowser


def main():
    try:
        with SentienceBrowser(headless=False) as browser:
            # Navigate to a page to ensure extension is active
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("networkidle")
            
            # Check if extension API is available
            bridge_ok = browser.page.evaluate("""
                () => {
                    return typeof window.sentience !== 'undefined' && 
                           typeof window.sentience.snapshot === 'function';
                }
            """)
            print(f"bridge_ok={bridge_ok}")
            
            if bridge_ok:
                print("✅ Extension loaded successfully!")
                # Try a quick snapshot to verify it works
                try:
                    result = browser.page.evaluate("window.sentience.snapshot({ limit: 1 })")
                    if result.get("status") == "success":
                        print(f"✅ Snapshot test: Found {len(result.get('elements', []))} elements")
                    else:
                        print(f"⚠️  Snapshot returned: {result.get('status')}")
                except Exception as e:
                    print(f"⚠️  Snapshot test failed: {e}")
            else:
                print("❌ Extension not loaded")
                # Debug info
                debug_info = browser.page.evaluate("""
                    () => {
                        return {
                            sentience_defined: typeof window.sentience !== 'undefined',
                            registry_defined: typeof window.sentience_registry !== 'undefined',
                            snapshot_defined: typeof window.sentience?.snapshot !== 'undefined'
                        };
                    }
                """)
                print(f"Debug info: {debug_info}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

