"""
Playwright browser harness with extension loading
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright

# Import stealth for bot evasion (optional - graceful fallback if not available)
try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False


class SentienceBrowser:
    """Main browser session with Sentience extension loaded"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        headless: bool = False
    ):
        """
        Initialize Sentience browser
        
        Args:
            api_key: Optional API key for server-side processing (Pro/Enterprise tiers)
                    If None, uses free tier (local extension only)
            api_url: Server URL for API calls (defaults to https://api.sentienceapi.com if api_key provided)
                    If None and api_key is provided, uses default URL
                    If None and no api_key, uses free tier (local extension only)
                    If 'local' or Docker sidecar URL, uses Enterprise tier
            headless: Whether to run in headless mode
        """
        self.api_key = api_key
        # Only set api_url if api_key is provided, otherwise None (free tier)
        # Default to https://api.sentienceapi.com if api_key is provided but api_url is not
        if api_key:
            self.api_url = api_url or "https://api.sentienceapi.com"
        else:
            self.api_url = None
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._extension_path: Optional[str] = None
    
    def start(self) -> None:
        """Launch browser with extension loaded"""
        # Get extension path (sentience-chrome directory)
        # __file__ is sdk-python/sentience/browser.py, so:
        # parent = sdk-python/sentience/
        # parent.parent = sdk-python/
        # parent.parent.parent = Sentience/ (project root)
        repo_root = Path(__file__).parent.parent.parent
        extension_source = repo_root / "sentience-chrome"
        
        if not extension_source.exists():
            raise FileNotFoundError(
                f"Extension not found at {extension_source}. "
                "Make sure sentience-chrome directory exists."
            )
        
        # Create temporary extension bundle
        temp_dir = tempfile.mkdtemp(prefix="sentience-ext-")
        self._extension_path = temp_dir
        
        # Copy extension files
        files_to_copy = [
            "manifest.json",
            "content.js",
            "background.js",
            "injected_api.js",
        ]
        
        for file in files_to_copy:
            src = extension_source / file
            if src.exists():
                shutil.copy2(src, os.path.join(temp_dir, file))
        
        # Copy pkg directory (WASM)
        pkg_source = extension_source / "pkg"
        if pkg_source.exists():
            pkg_dest = os.path.join(temp_dir, "pkg")
            shutil.copytree(pkg_source, pkg_dest, dirs_exist_ok=True)
        else:
            raise FileNotFoundError(
                f"WASM files not found at {pkg_source}. "
                "Build the extension first: cd sentience-chrome && ./build.sh"
            )
        
        # Launch Playwright
        self.playwright = sync_playwright().start()
        
        # Stealth arguments for bot evasion
        stealth_args = [
            f"--load-extension={temp_dir}",
            f"--disable-extensions-except={temp_dir}",
            "--disable-blink-features=AutomationControlled",  # Hide automation indicators
            "--no-sandbox",  # Required for some environments
            "--disable-infobars",  # Hide "Chrome is being controlled" message
        ]
        
        # Realistic viewport and user-agent for better evasion
        viewport_config = {"width": 1920, "height": 1080}
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        # Launch browser with extension
        # Note: channel="chrome" (system Chrome) has known issues with extension loading
        # We use bundled Chromium for reliable extension loading, but still apply stealth features
        user_data_dir = tempfile.mkdtemp(prefix="sentience-profile-")
        use_chrome_channel = False  # Disable for now due to extension loading issues
        
        try:
            if use_chrome_channel:
                # Try with system Chrome first (better evasion, but may have extension issues)
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel="chrome",  # Use system Chrome (better evasion)
                    headless=self.headless,
                    args=stealth_args,
                    viewport=viewport_config,
                    user_agent=user_agent,
                    timeout=30000,
                )
            else:
                # Use bundled Chromium (more reliable for extensions)
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=self.headless,
                    args=stealth_args,
                    viewport=viewport_config,
                    user_agent=user_agent,
                    timeout=30000,
                )
        except Exception as launch_error:
            # Clean up on failure
            if os.path.exists(user_data_dir):
                try:
                    shutil.rmtree(user_data_dir)
                except Exception:
                    pass
            raise RuntimeError(
                f"Failed to launch browser: {launch_error}\n"
                "Make sure Playwright browsers are installed: playwright install chromium"
            ) from launch_error
        
        # Get first page or create new one
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = self.context.new_page()
        
        # Apply stealth patches for bot evasion (if available)
        if STEALTH_AVAILABLE:
            try:
                stealth_sync(self.page)
            except Exception:
                # Silently fail if stealth application fails - not critical
                # This is expected if playwright-stealth has compatibility issues
                pass
        
        # Verify extension is loaded by checking background page
        # This helps catch extension loading issues early
        try:
            background_pages = [p for p in self.context.background_pages]
            if not background_pages:
                # Extension might not have a background page, or it's not loaded yet
                # Wait a bit for extension to initialize
                self.page.wait_for_timeout(1000)
        except Exception:
            # Background pages might not be accessible, continue anyway
            pass
        
        # Navigate to a real page so extension can inject
        # Extension content scripts only run on actual pages (not about:blank)
        # Use a simple page that loads quickly
        self.page.goto("https://example.com", wait_until="domcontentloaded", timeout=15000)
        
        # Give extension time to initialize (WASM loading is async)
        # Content scripts run at document_idle, so we need to wait for that
        # Also wait for extension ID to be set by content.js
        self.page.wait_for_timeout(3000)
        
        # Wait for extension to load
        if not self._wait_for_extension(timeout=25000):
            # Extension might need more time, try waiting a bit longer
            self.page.wait_for_timeout(3000)
            if not self._wait_for_extension(timeout=15000):
                # Get diagnostic info before failing
                try:
                    diagnostic_info = self.page.evaluate("""
                        () => {
                            const info = {
                                sentience_defined: typeof window.sentience !== 'undefined',
                                registry_defined: typeof window.sentience_registry !== 'undefined',
                                snapshot_defined: typeof window.sentience?.snapshot === 'function',
                                extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                                url: window.location.href
                            };
                            if (window.sentience) {
                                info.sentience_keys = Object.keys(window.sentience);
                            }
                            return info;
                        }
                    """)
                    diagnostic_str = f"\n5. Diagnostic info: {diagnostic_info}"
                except Exception:
                    diagnostic_str = "\n5. Could not get diagnostic info"
                
                raise RuntimeError(
                    "Extension failed to load after navigation. Make sure:\n"
                    "1. Extension is built (cd sentience-chrome && ./build.sh)\n"
                    "2. All files are present (manifest.json, content.js, injected_api.js, pkg/)\n"
                    "3. Check browser console for errors (run with headless=False to see console)\n"
                    f"4. Extension path: {temp_dir}"
                    + diagnostic_str
                )
    
    def _wait_for_extension(self, timeout: int = 20000) -> bool:
        """Wait for window.sentience API to be available"""
        import time
        start = time.time()
        last_error = None
        
        while time.time() - start < timeout / 1000:
            try:
                result = self.page.evaluate("""
                    () => {
                        // Check if sentience API exists
                        if (typeof window.sentience === 'undefined') {
                            return { ready: false, reason: 'window.sentience not defined' };
                        }
                        // Check if snapshot function exists
                        if (typeof window.sentience.snapshot !== 'function') {
                            return { ready: false, reason: 'snapshot function not available' };
                        }
                        // Check if registry is initialized
                        if (window.sentience_registry === undefined) {
                            return { ready: false, reason: 'registry not initialized' };
                        }
                        // Check if WASM module is loaded (check internal _wasmModule if available)
                        const sentience = window.sentience;
                        if (sentience._wasmModule && !sentience._wasmModule.analyze_page) {
                            return { ready: false, reason: 'WASM module not fully loaded' };
                        }
                        // If _wasmModule is not exposed, that's okay - it might be internal
                        // Just verify the API structure is correct
                        return { ready: true };
                    }
                """)
                
                if isinstance(result, dict):
                    if result.get("ready"):
                        return True
                    last_error = result.get("reason", "Unknown error")
            except Exception as e:
                # Continue waiting on errors
                last_error = f"Evaluation error: {str(e)}"
            
            time.sleep(0.3)
        
        # Log the last error for debugging
        if last_error:
            import warnings
            warnings.warn(f"Extension wait timeout. Last status: {last_error}")
        
        return False
    
    def close(self) -> None:
        """Close browser and cleanup"""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        if self._extension_path and os.path.exists(self._extension_path):
            shutil.rmtree(self._extension_path)
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

