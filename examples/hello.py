"""
Day 2 Example: Verify extension bridge is loaded
"""

from sentience import SentienceBrowser


def main():
    with SentienceBrowser(headless=False) as browser:
        # Check if extension API is available
        bridge_ok = browser.page.evaluate("typeof window.sentience !== 'undefined'")
        print(f"bridge_ok={bridge_ok}")
        
        if bridge_ok:
            print("✅ Extension loaded successfully!")
        else:
            print("❌ Extension not loaded")


if __name__ == "__main__":
    main()

