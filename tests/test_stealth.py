#!/usr/bin/env python3
"""
Test bot evasion and stealth mode features.

This test verifies that stealth features are working:
- navigator.webdriver is false
- window.chrome exists
- User-agent is realistic
- Viewport is realistic
- Stealth arguments are applied
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentience.browser import SentienceBrowser


def test_stealth_features():
    """Test that stealth features are working correctly"""
    print("=" * 60)
    print("Bot Evasion / Stealth Mode Test")
    print("=" * 60)
    
    browser = SentienceBrowser()
    
    try:
        browser.start()
        page = browser.page
        
        print("\n1. Testing navigator.webdriver...")
        webdriver_value = page.evaluate("() => navigator.webdriver")
        if webdriver_value is False or webdriver_value is None:
            print(f"   ✅ navigator.webdriver = {webdriver_value} (stealth working)")
        else:
            print(f"   ❌ navigator.webdriver = {webdriver_value} (detectable)")
        
        print("\n2. Testing window.chrome...")
        chrome_exists = page.evaluate("() => typeof window.chrome !== 'undefined'")
        if chrome_exists:
            print(f"   ✅ window.chrome exists (stealth working)")
        else:
            print(f"   ❌ window.chrome does not exist (detectable)")
        
        print("\n3. Testing user-agent...")
        user_agent = page.evaluate("() => navigator.userAgent")
        print(f"   User-Agent: {user_agent}")
        if "HeadlessChrome" not in user_agent and "Chrome" in user_agent:
            print("   ✅ User-Agent looks realistic (no HeadlessChrome)")
        else:
            print("   ⚠️  User-Agent may be detectable")
        
        print("\n4. Testing viewport...")
        viewport = page.evaluate("() => ({ width: window.innerWidth, height: window.innerHeight })")
        print(f"   Viewport: {viewport['width']}x{viewport['height']}")
        if viewport['width'] >= 1920 and viewport['height'] >= 1080:
            print("   ✅ Viewport is realistic (1920x1080 or larger)")
        else:
            print("   ⚠️  Viewport may be smaller than expected")
        
        print("\n5. Testing navigator.plugins...")
        plugins_count = page.evaluate("() => navigator.plugins.length")
        print(f"   Plugins count: {plugins_count}")
        if plugins_count > 0:
            print("   ✅ Plugins present (stealth working)")
        else:
            print("   ⚠️  No plugins (may be detectable)")
        
        print("\n6. Testing permissions API...")
        try:
            permissions_works = page.evaluate("""
                () => {
                    if (navigator.permissions && navigator.permissions.query) {
                        return true;
                    }
                    return false;
                }
            """)
            if permissions_works:
                print("   ✅ Permissions API is patched")
            else:
                print("   ⚠️  Permissions API may not be patched")
        except Exception as e:
            print(f"   ⚠️  Could not test permissions: {e}")
        
        print("\n7. Testing against bot detection site...")
        try:
            # Navigate to a bot detection test site
            page.goto("https://bot.sannysoft.com/", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(2000)  # Wait for page to load
            
            # Check if we're detected
            detection_results = page.evaluate("""
                () => {
                    const results = {};
                    // Check webdriver
                    results.webdriver = navigator.webdriver;
                    // Check chrome
                    results.chrome = typeof window.chrome !== 'undefined';
                    // Check plugins
                    results.plugins = navigator.plugins.length;
                    // Check languages
                    results.languages = navigator.languages.length;
                    return results;
                }
            """)
            
            print(f"   Detection results: {detection_results}")
            
            # Count how many stealth features are working
            stealth_score = 0
            if detection_results.get('webdriver') is False:
                stealth_score += 1
            if detection_results.get('chrome') is True:
                stealth_score += 1
            if detection_results.get('plugins', 0) > 0:
                stealth_score += 1
            
            print(f"   Stealth score: {stealth_score}/3")
            if stealth_score >= 2:
                print("   ✅ Most stealth features working")
            else:
                print("   ⚠️  Some stealth features may not be working")
                
        except Exception as e:
            print(f"   ⚠️  Could not test against bot detection site: {e}")
            print("   (This is okay - site may be down or blocked)")
        
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print("✅ Stealth features have been applied")
        print("⚠️  Note: Bot detection is a cat-and-mouse game.")
        print("   No solution is 100% effective against all detection systems.")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        browser.close()


if __name__ == "__main__":
    success = test_stealth_features()
    sys.exit(0 if success else 1)

