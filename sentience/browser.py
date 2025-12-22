"""
Playwright browser harness with extension loading
"""

import os
import tempfile
import shutil
import time
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
        headless: Optional[bool] = None
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
            headless: Whether to run in headless mode. If None, defaults to True in CI, False otherwise
        """
        self.api_key = api_key
        # Only set api_url if api_key is provided, otherwise None (free tier)
        # Defaults to production API if key is present but url is missing
        if self.api_key and not api_url:
            self.api_url = "https://api.sentienceapi.com"
        else:
            self.api_url = api_url
            
        # Determine headless mode
        if headless is None:
            # Default to False for local dev, True for CI
            self.headless = os.environ.get("CI", "").lower() == "true"
        else:
            self.headless = headless
            
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._extension_path: Optional[str] = None
    
    def start(self) -> None:
        """Launch browser with extension loaded"""
        # Get extension source path (relative to project root/package)
        # Handle both development (src/) and installed package cases
        
        # 1. Try relative to this file (installed package structure)
        # sentience/browser.py -> sentience/extension/
        package_ext_path = Path(__file__).parent / "extension"
        
        # 2. Try development root (if running from source repo)
        # sentience/browser.py -> ../sentience-chrome
        dev_ext_path = Path(__file__).parent.parent.parent / "sentience-chrome"
        
        if package_ext_path.exists() and (package_ext_path / "manifest.json").exists():
            extension_source = package_ext_path
        elif dev_ext_path.exists() and (dev_ext_path / "manifest.json").exists():
            extension_source = dev_ext_path
        else:
            raise FileNotFoundError(
                f"Extension not found. Checked:\n"
                f"1. {package_ext_path}\n"
                f"2. {dev_ext_path}\n"
                "Make sure the extension is built and 'sentience/extension' directory exists."
            )

        # Create temporary extension bundle
        # We copy it to a temp dir to avoid file locking issues and ensure clean state
        self._extension_path = tempfile.mkdtemp(prefix="sentience-ext-")
        shutil.copytree(extension_source, self._extension_path, dirs_exist_ok=True)

        self.playwright = sync_playwright().start()

        # Build launch arguments
        args = [
            f"--disable-extensions-except={self._extension_path}",
            f"--load-extension={self._extension_path}",
            "--disable-blink-features=AutomationControlled", # Hides 'navigator.webdriver'
            "--no-sandbox",
            "--disable-infobars",
        ]

        # Handle headless mode correctly for extensions
        # 'headless=True' DOES NOT support extensions in standard Chrome
        # We must use 'headless="new"' (Chrome 112+) or run visible
        launch_headless_arg = False # Default to visible
        if self.headless:
            args.append("--headless=new") # Use new headless mode via args
        
        # Launch persistent context (required for extensions)
        # Note: We pass headless=False to launch_persistent_context because we handle
        # headless mode via the --headless=new arg above. This is a Playwright workaround.
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir="", # Ephemeral temp dir
            headless=False,   # IMPORTANT: See note above
            args=args,
            viewport={"width": 1280, "height": 800},
            # Remove "HeadlessChrome" from User Agent automatically
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

        # Apply stealth if available
        if STEALTH_AVAILABLE:
            stealth_sync(self.page)
            
        # Wait a moment for extension to initialize
        time.sleep(0.5)

    def goto(self, url: str) -> None:
        """Navigate to a URL and ensure extension is ready"""
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")
            
        self.page.goto(url, wait_until="domcontentloaded")
        
        # Wait for extension to be ready (injected into page)
        if not self._wait_for_extension():
            # Gather diagnostic info before failing
            try:
                diag = self.page.evaluate("""() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    registry_defined: typeof window.sentience_registry !== 'undefined',
                    snapshot_defined: window.sentience && typeof window.sentience.snapshot === 'function',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })""")
            except Exception as e:
                diag = f"Failed to get diagnostics: {str(e)}"

            raise RuntimeError(
                "Extension failed to load after navigation. Make sure:\n"
                "1. Extension is built (cd sentience-chrome && ./build.sh)\n"
                "2. All files are present (manifest.json, content.js, injected_api.js, pkg/)\n"
                "3. Check browser console for errors (run with headless=False to see console)\n"
                f"4. Extension path: {self._extension_path}\n"
                f"5. Diagnostic info: {diag}"
            )

    def _wait_for_extension(self, timeout_sec: float = 5.0) -> bool:
        """Poll for window.sentience to be available"""
        start_time = time.time()
        last_error = None
        
        while time.time() - start_time < timeout_sec:
            try:
                # Check if API exists and WASM is ready (optional check for _wasmModule)
                result = self.page.evaluate("""() => {
                        if (typeof window.sentience === 'undefined') {
                            return { ready: false, reason: 'window.sentience undefined' };
                        }
                        // Check if WASM loaded (if exposed) or if basic API works
                        // Note: injected_api.js defines window.sentience immediately, 
                        // but _wasmModule might take a few ms to load.
                        if (window.sentience._wasmModule === null) {
                             // It's defined but WASM isn't linked yet
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