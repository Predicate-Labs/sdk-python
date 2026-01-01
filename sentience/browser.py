"""
Playwright browser harness with extension loading
"""

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import BrowserContext as AsyncBrowserContext, Page as AsyncPage, Playwright as AsyncPlaywright, async_playwright
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from sentience._extension_loader import find_extension_path
from sentience.models import ProxyConfig, StorageState, Viewport

# Import stealth for bot evasion (optional - graceful fallback if not available)
try:
    from playwright_stealth import stealth_async, stealth_sync

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False


class SentienceBrowser:
    """Main browser session with Sentience extension loaded"""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        headless: bool | None = None,
        proxy: str | None = None,
        user_data_dir: str | None = None,
        storage_state: str | Path | StorageState | dict | None = None,
        record_video_dir: str | Path | None = None,
        record_video_size: dict[str, int] | None = None,
        viewport: Viewport | dict[str, int] | None = None,
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
            proxy: Optional proxy server URL (e.g., 'http://user:pass@proxy.example.com:8080')
                   Supports HTTP, HTTPS, and SOCKS5 proxies
                   Falls back to SENTIENCE_PROXY environment variable if not provided
            user_data_dir: Optional path to user data directory for persistent sessions.
                          If None, uses temporary directory (session not persisted).
                          If provided, cookies and localStorage persist across browser restarts.
            storage_state: Optional storage state to inject (cookies + localStorage).
                          Can be:
                          - Path to JSON file (str or Path)
                          - StorageState object
                          - Dictionary with 'cookies' and/or 'origins' keys
                          If provided, browser starts with pre-injected authentication.
            record_video_dir: Optional directory path to save video recordings.
                            If provided, browser will record video of all pages.
                            Videos are saved as .webm files in the specified directory.
                            If None, no video recording is performed.
            record_video_size: Optional video resolution as dict with 'width' and 'height' keys.
                             Examples: {"width": 1280, "height": 800} (default)
                                      {"width": 1920, "height": 1080} (1080p)
                             If None, defaults to 1280x800.
            viewport: Optional viewport size as Viewport object or dict with 'width' and 'height' keys.
                     Examples: Viewport(width=1280, height=800) (default)
                              Viewport(width=1920, height=1080) (Full HD)
                              {"width": 1280, "height": 800} (dict also supported)
                     If None, defaults to Viewport(width=1280, height=800).
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

        # Support proxy from argument or environment variable
        self.proxy = proxy or os.environ.get("SENTIENCE_PROXY")

        # Auth injection support
        self.user_data_dir = user_data_dir
        self.storage_state = storage_state

        # Video recording support
        self.record_video_dir = record_video_dir
        self.record_video_size = record_video_size or {"width": 1280, "height": 800}

        # Viewport configuration - convert dict to Viewport if needed
        if viewport is None:
            self.viewport = Viewport(width=1280, height=800)
        elif isinstance(viewport, dict):
            self.viewport = Viewport(width=viewport["width"], height=viewport["height"])
        else:
            self.viewport = viewport

        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._extension_path: str | None = None

    def _parse_proxy(self, proxy_string: str) -> ProxyConfig | None:
        """
        Parse proxy connection string into ProxyConfig.

        Args:
            proxy_string: Proxy URL (e.g., 'http://user:pass@proxy.example.com:8080')

        Returns:
            ProxyConfig object or None if invalid

        Raises:
            ValueError: If proxy format is invalid
        """
        if not proxy_string:
            return None

        try:
            parsed = urlparse(proxy_string)

            # Validate scheme
            if parsed.scheme not in ("http", "https", "socks5"):
                print(f"⚠️  [Sentience] Unsupported proxy scheme: {parsed.scheme}")
                print("   Supported: http, https, socks5")
                return None

            # Validate host and port
            if not parsed.hostname or not parsed.port:
                print("⚠️  [Sentience] Proxy URL must include hostname and port")
                print("   Expected format: http://username:password@host:port")
                return None

            # Build server URL
            server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"

            # Create ProxyConfig with optional credentials
            return ProxyConfig(
                server=server,
                username=parsed.username if parsed.username else None,
                password=parsed.password if parsed.password else None,
            )

        except Exception as e:
            print(f"⚠️  [Sentience] Invalid proxy configuration: {e}")
            print("   Expected format: http://username:password@host:port")
            return None

    def start(self) -> None:
        """Launch browser with extension loaded"""
        # Get extension source path using shared utility
        extension_source = find_extension_path()

        # Create temporary extension bundle
        # We copy it to a temp dir to avoid file locking issues and ensure clean state
        self._extension_path = tempfile.mkdtemp(prefix="sentience-ext-")
        shutil.copytree(extension_source, self._extension_path, dirs_exist_ok=True)

        self.playwright = sync_playwright().start()

        # Build launch arguments
        args = [
            f"--disable-extensions-except={self._extension_path}",
            f"--load-extension={self._extension_path}",
            "--disable-blink-features=AutomationControlled",  # Hides 'navigator.webdriver'
            "--no-sandbox",
            "--disable-infobars",
            # WebRTC leak protection (prevents real IP exposure when using proxies/VPNs)
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ]

        # Handle headless mode correctly for extensions
        # 'headless=True' DOES NOT support extensions in standard Chrome
        # We must use 'headless="new"' (Chrome 112+) or run visible
        # launch_headless_arg = False  # Default to visible
        if self.headless:
            args.append("--headless=new")  # Use new headless mode via args

        # Parse proxy configuration if provided
        proxy_config = self._parse_proxy(self.proxy) if self.proxy else None

        # Handle User Data Directory (Persistence)
        if self.user_data_dir:
            user_data_dir = str(self.user_data_dir)
            Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        else:
            user_data_dir = ""  # Ephemeral temp dir (existing behavior)

        # Build launch_persistent_context parameters
        launch_params = {
            "user_data_dir": user_data_dir,
            "headless": False,  # IMPORTANT: See note above
            "args": args,
            "viewport": {"width": self.viewport.width, "height": self.viewport.height},
            # Remove "HeadlessChrome" from User Agent automatically
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

        # Add proxy if configured
        if proxy_config:
            launch_params["proxy"] = proxy_config.to_playwright_dict()
            # Ignore HTTPS errors when using proxy (many residential proxies use self-signed certs)
            launch_params["ignore_https_errors"] = True
            print(f"🌐 [Sentience] Using proxy: {proxy_config.server}")

        # Add video recording if configured
        if self.record_video_dir:
            video_dir = Path(self.record_video_dir)
            video_dir.mkdir(parents=True, exist_ok=True)
            launch_params["record_video_dir"] = str(video_dir)
            launch_params["record_video_size"] = self.record_video_size
            print(f"🎥 [Sentience] Recording video to: {video_dir}")
            print(
                f"   Resolution: {self.record_video_size['width']}x{self.record_video_size['height']}"
            )

        # Launch persistent context (required for extensions)
        # Note: We pass headless=False to launch_persistent_context because we handle
        # headless mode via the --headless=new arg above. This is a Playwright workaround.
        self.context = self.playwright.chromium.launch_persistent_context(**launch_params)

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

        # Inject storage state if provided (must be after context creation)
        if self.storage_state:
            self._inject_storage_state(self.storage_state)

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
                diag = self.page.evaluate(
                    """() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    registry_defined: typeof window.sentience_registry !== 'undefined',
                    snapshot_defined: window.sentience && typeof window.sentience.snapshot === 'function',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })"""
                )
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

    def _inject_storage_state(
        self, storage_state: str | Path | StorageState | dict
    ) -> None:  # noqa: C901
        """
        Inject storage state (cookies + localStorage) into browser context.

        Args:
            storage_state: Path to JSON file, StorageState object, or dict containing storage state
        """
        import json

        # Load storage state
        if isinstance(storage_state, (str, Path)):
            # Load from file
            with open(storage_state, encoding="utf-8") as f:
                state_dict = json.load(f)
            state = StorageState.from_dict(state_dict)
        elif isinstance(storage_state, StorageState):
            # Already a StorageState object
            state = storage_state
        elif isinstance(storage_state, dict):
            # Dictionary format
            state = StorageState.from_dict(storage_state)
        else:
            raise ValueError(
                f"Invalid storage_state type: {type(storage_state)}. "
                "Expected str, Path, StorageState, or dict."
            )

        # Inject cookies (works globally)
        if state.cookies:
            # Convert to Playwright cookie format
            playwright_cookies = []
            for cookie in state.cookies:
                cookie_dict = cookie.model_dump()
                # Playwright expects lowercase keys for some fields
                playwright_cookie = {
                    "name": cookie_dict["name"],
                    "value": cookie_dict["value"],
                    "domain": cookie_dict["domain"],
                    "path": cookie_dict["path"],
                }
                if cookie_dict.get("expires"):
                    playwright_cookie["expires"] = cookie_dict["expires"]
                if cookie_dict.get("httpOnly"):
                    playwright_cookie["httpOnly"] = cookie_dict["httpOnly"]
                if cookie_dict.get("secure"):
                    playwright_cookie["secure"] = cookie_dict["secure"]
                if cookie_dict.get("sameSite"):
                    playwright_cookie["sameSite"] = cookie_dict["sameSite"]
                playwright_cookies.append(playwright_cookie)

            self.context.add_cookies(playwright_cookies)
            print(f"✅ [Sentience] Injected {len(state.cookies)} cookie(s)")

        # Inject LocalStorage (requires navigation to each domain)
        if state.origins:
            for origin_data in state.origins:
                origin = origin_data.origin
                if not origin:
                    continue

                # Navigate to origin to set localStorage
                try:
                    self.page.goto(origin, wait_until="domcontentloaded", timeout=10000)

                    # Inject localStorage
                    if origin_data.localStorage:
                        # Convert to dict format for JavaScript
                        localStorage_dict = {
                            item.name: item.value for item in origin_data.localStorage
                        }
                        self.page.evaluate(
                            """(localStorage_data) => {
                                for (const [key, value] of Object.entries(localStorage_data)) {
                                    localStorage.setItem(key, value);
                                }
                            }""",
                            localStorage_dict,
                        )
                        print(
                            f"✅ [Sentience] Injected {len(origin_data.localStorage)} localStorage item(s) for {origin}"
                        )
                except Exception as e:
                    print(f"⚠️  [Sentience] Failed to inject localStorage for {origin}: {e}")

    def _wait_for_extension(self, timeout_sec: float = 5.0) -> bool:
        """Poll for window.sentience to be available"""
        start_time = time.time()
        last_error = None

        while time.time() - start_time < timeout_sec:
            try:
                # Check if API exists and WASM is ready (optional check for _wasmModule)
                result = self.page.evaluate(
                    """() => {
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
                """
                )

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

    def close(self, output_path: str | Path | None = None) -> str | None:
        """
        Close browser and cleanup

        Args:
            output_path: Optional path to rename the video file to.
                        If provided, the recorded video will be moved to this location.
                        Useful for giving videos meaningful names instead of random hashes.

        Returns:
            Path to video file if recording was enabled, None otherwise
            Note: Video files are saved automatically by Playwright when context closes.
            If multiple pages exist, returns the path to the first page's video.
        """
        temp_video_path = None

        # Get video path before closing (if recording was enabled)
        # Note: Playwright saves videos when pages/context close, but we can get the
        # expected path before closing. The actual file will be available after close.
        if self.record_video_dir:
            try:
                # Try to get video path from the first page
                if self.page and self.page.video:
                    temp_video_path = self.page.video.path()
                # If that fails, check all pages in the context
                elif self.context:
                    for page in self.context.pages:
                        if page.video:
                            temp_video_path = page.video.path()
                            break
            except Exception:
                # Video path might not be available until after close
                # In that case, we'll return None and user can check the directory
                pass

        # Close context (this triggers video file finalization)
        if self.context:
            self.context.close()

        # Close playwright
        if self.playwright:
            self.playwright.stop()

        # Clean up extension directory
        if self._extension_path and os.path.exists(self._extension_path):
            shutil.rmtree(self._extension_path)

        # Rename/move video if output_path is specified
        final_path = temp_video_path
        if temp_video_path and output_path and os.path.exists(temp_video_path):
            try:
                output_path = str(output_path)
                # Ensure parent directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(temp_video_path, output_path)
                final_path = output_path
            except Exception as e:
                import warnings

                warnings.warn(f"Failed to rename video file: {e}")
                # Return original path if rename fails
                final_path = temp_video_path

        return final_path

    @classmethod
    def from_existing(
        cls,
        context: BrowserContext,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "SentienceBrowser":
        """
        Create SentienceBrowser from an existing Playwright BrowserContext.

        This allows you to use Sentience SDK with a browser context you've already created,
        giving you more control over browser initialization.

        Args:
            context: Existing Playwright BrowserContext
            api_key: Optional API key for server-side processing
            api_url: Optional API URL (defaults to https://api.sentienceapi.com if api_key provided)

        Returns:
            SentienceBrowser instance configured to use the existing context

        Example:
            from playwright.sync_api import sync_playwright
            from sentience import SentienceBrowser, snapshot

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(...)
                browser = SentienceBrowser.from_existing(context)
                browser.page.goto("https://example.com")
                snap = snapshot(browser)
        """
        instance = cls(api_key=api_key, api_url=api_url)
        instance.context = context
        instance.page = context.pages[0] if context.pages else context.new_page()

        # Apply stealth if available
        if STEALTH_AVAILABLE:
            stealth_sync(instance.page)

        # Wait for extension to be ready (if extension is loaded)
        time.sleep(0.5)

        return instance

    @classmethod
    def from_page(
        cls,
        page: Page,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "SentienceBrowser":
        """
        Create SentienceBrowser from an existing Playwright Page.

        This allows you to use Sentience SDK with a page you've already created,
        giving you more control over browser initialization.

        Args:
            page: Existing Playwright Page
            api_key: Optional API key for server-side processing
            api_url: Optional API URL (defaults to https://api.sentienceapi.com if api_key provided)

        Returns:
            SentienceBrowser instance configured to use the existing page

        Example:
            from playwright.sync_api import sync_playwright
            from sentience import SentienceBrowser, snapshot

            with sync_playwright() as p:
                browser_instance = p.chromium.launch()
                context = browser_instance.new_context()
                page = context.new_page()
                page.goto("https://example.com")

                browser = SentienceBrowser.from_page(page)
                snap = snapshot(browser)
        """
        instance = cls(api_key=api_key, api_url=api_url)
        instance.page = page
        instance.context = page.context

        # Apply stealth if available
        if STEALTH_AVAILABLE:
            stealth_sync(instance.page)

        # Wait for extension to be ready (if extension is loaded)
        time.sleep(0.5)

        return instance

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class AsyncSentienceBrowser:
    """Async version of SentienceBrowser for use in asyncio contexts."""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        headless: bool | None = None,
        proxy: str | None = None,
        user_data_dir: str | Path | None = None,
        storage_state: str | Path | StorageState | dict | None = None,
        record_video_dir: str | Path | None = None,
        record_video_size: dict[str, int] | None = None,
        viewport: Viewport | dict[str, int] | None = None,
    ):
        """
        Initialize Async Sentience browser

        Args:
            api_key: Optional API key for server-side processing (Pro/Enterprise tiers)
                    If None, uses free tier (local extension only)
            api_url: Server URL for API calls (defaults to https://api.sentienceapi.com if api_key provided)
            headless: Whether to run in headless mode. If None, defaults to True in CI, False otherwise
            proxy: Optional proxy server URL (e.g., 'http://user:pass@proxy.example.com:8080')
            user_data_dir: Optional path to user data directory for persistent sessions
            storage_state: Optional storage state to inject (cookies + localStorage)
            record_video_dir: Optional directory path to save video recordings
            record_video_size: Optional video resolution as dict with 'width' and 'height' keys
            viewport: Optional viewport size as Viewport object or dict with 'width' and 'height' keys.
                     Examples: Viewport(width=1280, height=800) (default)
                              Viewport(width=1920, height=1080) (Full HD)
                              {"width": 1280, "height": 800} (dict also supported)
                     If None, defaults to Viewport(width=1280, height=800).
        """
        self.api_key = api_key
        # Only set api_url if api_key is provided, otherwise None (free tier)
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

        # Support proxy from argument or environment variable
        self.proxy = proxy or os.environ.get("SENTIENCE_PROXY")

        # Auth injection support
        self.user_data_dir = user_data_dir
        self.storage_state = storage_state

        # Video recording support
        self.record_video_dir = record_video_dir
        self.record_video_size = record_video_size or {"width": 1280, "height": 800}

        # Viewport configuration - convert dict to Viewport if needed
        if viewport is None:
            self.viewport = Viewport(width=1280, height=800)
        elif isinstance(viewport, dict):
            self.viewport = Viewport(width=viewport["width"], height=viewport["height"])
        else:
            self.viewport = viewport

        self.playwright: AsyncPlaywright | None = None
        self.context: AsyncBrowserContext | None = None
        self.page: AsyncPage | None = None
        self._extension_path: str | None = None

    def _parse_proxy(self, proxy_string: str) -> ProxyConfig | None:
        """
        Parse proxy connection string into ProxyConfig.

        Args:
            proxy_string: Proxy URL (e.g., 'http://user:pass@proxy.example.com:8080')

        Returns:
            ProxyConfig object or None if invalid
        """
        if not proxy_string:
            return None

        try:
            parsed = urlparse(proxy_string)

            # Validate scheme
            if parsed.scheme not in ("http", "https", "socks5"):
                print(f"⚠️  [Sentience] Unsupported proxy scheme: {parsed.scheme}")
                print("   Supported: http, https, socks5")
                return None

            # Validate host and port
            if not parsed.hostname or not parsed.port:
                print("⚠️  [Sentience] Proxy URL must include hostname and port")
                print("   Expected format: http://username:password@host:port")
                return None

            # Build server URL
            server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"

            # Create ProxyConfig with optional credentials
            return ProxyConfig(
                server=server,
                username=parsed.username if parsed.username else None,
                password=parsed.password if parsed.password else None,
            )

        except Exception as e:
            print(f"⚠️  [Sentience] Invalid proxy configuration: {e}")
            print("   Expected format: http://username:password@host:port")
            return None

    async def start(self) -> None:
        """Launch browser with extension loaded (async)"""
        # Get extension source path using shared utility
        extension_source = find_extension_path()

        # Create temporary extension bundle
        self._extension_path = tempfile.mkdtemp(prefix="sentience-ext-")
        shutil.copytree(extension_source, self._extension_path, dirs_exist_ok=True)

        self.playwright = await async_playwright().start()

        # Build launch arguments
        args = [
            f"--disable-extensions-except={self._extension_path}",
            f"--load-extension={self._extension_path}",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ]

        if self.headless:
            args.append("--headless=new")

        # Parse proxy configuration if provided
        proxy_config = self._parse_proxy(self.proxy) if self.proxy else None

        # Handle User Data Directory
        if self.user_data_dir:
            user_data_dir = str(self.user_data_dir)
            Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        else:
            user_data_dir = ""

        # Build launch_persistent_context parameters
        launch_params = {
            "user_data_dir": user_data_dir,
            "headless": False,
            "args": args,
            "viewport": {"width": self.viewport.width, "height": self.viewport.height},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

        # Add proxy if configured
        if proxy_config:
            launch_params["proxy"] = proxy_config.to_playwright_dict()
            launch_params["ignore_https_errors"] = True
            print(f"🌐 [Sentience] Using proxy: {proxy_config.server}")

        # Add video recording if configured
        if self.record_video_dir:
            video_dir = Path(self.record_video_dir)
            video_dir.mkdir(parents=True, exist_ok=True)
            launch_params["record_video_dir"] = str(video_dir)
            launch_params["record_video_size"] = self.record_video_size
            print(f"🎥 [Sentience] Recording video to: {video_dir}")
            print(
                f"   Resolution: {self.record_video_size['width']}x{self.record_video_size['height']}"
            )

        # Launch persistent context
        self.context = await self.playwright.chromium.launch_persistent_context(**launch_params)

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Inject storage state if provided
        if self.storage_state:
            await self._inject_storage_state(self.storage_state)

        # Apply stealth if available
        if STEALTH_AVAILABLE:
            await stealth_async(self.page)

        # Wait a moment for extension to initialize
        await asyncio.sleep(0.5)

    async def goto(self, url: str) -> None:
        """Navigate to a URL and ensure extension is ready (async)"""
        if not self.page:
            raise RuntimeError("Browser not started. Call await start() first.")

        await self.page.goto(url, wait_until="domcontentloaded")

        # Wait for extension to be ready
        if not await self._wait_for_extension():
            try:
                diag = await self.page.evaluate(
                    """() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    registry_defined: typeof window.sentience_registry !== 'undefined',
                    snapshot_defined: window.sentience && typeof window.sentience.snapshot === 'function',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })"""
                )
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

    async def _inject_storage_state(self, storage_state: str | Path | StorageState | dict) -> None:
        """Inject storage state (cookies + localStorage) into browser context (async)"""
        import json

        # Load storage state
        if isinstance(storage_state, (str, Path)):
            with open(storage_state, encoding="utf-8") as f:
                state_dict = json.load(f)
            state = StorageState.from_dict(state_dict)
        elif isinstance(storage_state, StorageState):
            state = storage_state
        elif isinstance(storage_state, dict):
            state = StorageState.from_dict(storage_state)
        else:
            raise ValueError(
                f"Invalid storage_state type: {type(storage_state)}. "
                "Expected str, Path, StorageState, or dict."
            )

        # Inject cookies
        if state.cookies:
            playwright_cookies = []
            for cookie in state.cookies:
                cookie_dict = cookie.model_dump()
                playwright_cookie = {
                    "name": cookie_dict["name"],
                    "value": cookie_dict["value"],
                    "domain": cookie_dict["domain"],
                    "path": cookie_dict["path"],
                }
                if cookie_dict.get("expires"):
                    playwright_cookie["expires"] = cookie_dict["expires"]
                if cookie_dict.get("httpOnly"):
                    playwright_cookie["httpOnly"] = cookie_dict["httpOnly"]
                if cookie_dict.get("secure"):
                    playwright_cookie["secure"] = cookie_dict["secure"]
                if cookie_dict.get("sameSite"):
                    playwright_cookie["sameSite"] = cookie_dict["sameSite"]
                playwright_cookies.append(playwright_cookie)

            await self.context.add_cookies(playwright_cookies)
            print(f"✅ [Sentience] Injected {len(state.cookies)} cookie(s)")

        # Inject LocalStorage
        if state.origins:
            for origin_data in state.origins:
                origin = origin_data.origin
                if not origin:
                    continue

                try:
                    await self.page.goto(origin, wait_until="domcontentloaded", timeout=10000)

                    if origin_data.localStorage:
                        localStorage_dict = {
                            item.name: item.value for item in origin_data.localStorage
                        }
                        await self.page.evaluate(
                            """(localStorage_data) => {
                                for (const [key, value] of Object.entries(localStorage_data)) {
                                    localStorage.setItem(key, value);
                                }
                            }""",
                            localStorage_dict,
                        )
                        print(
                            f"✅ [Sentience] Injected {len(origin_data.localStorage)} localStorage item(s) for {origin}"
                        )
                except Exception as e:
                    print(f"⚠️  [Sentience] Failed to inject localStorage for {origin}: {e}")

    async def _wait_for_extension(self, timeout_sec: float = 5.0) -> bool:
        """Poll for window.sentience to be available (async)"""
        start_time = time.time()
        last_error = None

        while time.time() - start_time < timeout_sec:
            try:
                result = await self.page.evaluate(
                    """() => {
                        if (typeof window.sentience === 'undefined') {
                            return { ready: false, reason: 'window.sentience undefined' };
                        }
                        if (window.sentience._wasmModule === null) {
                             return { ready: false, reason: 'WASM module not fully loaded' };
                        }
                        return { ready: true };
                    }
                """
                )

                if isinstance(result, dict):
                    if result.get("ready"):
                        return True
                    last_error = result.get("reason", "Unknown error")
            except Exception as e:
                last_error = f"Evaluation error: {str(e)}"

            await asyncio.sleep(0.3)

        if last_error:
            import warnings

            warnings.warn(f"Extension wait timeout. Last status: {last_error}")

        return False

    async def close(self, output_path: str | Path | None = None) -> str | None:
        """
        Close browser and cleanup (async)

        Args:
            output_path: Optional path to rename the video file to

        Returns:
            Path to video file if recording was enabled, None otherwise
        """
        temp_video_path = None

        if self.record_video_dir:
            try:
                if self.page and self.page.video:
                    temp_video_path = await self.page.video.path()
                elif self.context:
                    for page in self.context.pages:
                        if page.video:
                            temp_video_path = await page.video.path()
                            break
            except Exception:
                pass

        if self.context:
            await self.context.close()
            self.context = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        if self._extension_path and os.path.exists(self._extension_path):
            shutil.rmtree(self._extension_path)

        # Clear page reference after closing context
        self.page = None

        final_path = temp_video_path
        if temp_video_path and output_path and os.path.exists(temp_video_path):
            try:
                output_path = str(output_path)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(temp_video_path, output_path)
                final_path = output_path
            except Exception as e:
                import warnings

                warnings.warn(f"Failed to rename video file: {e}")
                final_path = temp_video_path

        return final_path

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    @classmethod
    async def from_existing(
        cls,
        context: AsyncBrowserContext,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "AsyncSentienceBrowser":
        """
        Create AsyncSentienceBrowser from an existing Playwright BrowserContext.

        Args:
            context: Existing Playwright BrowserContext
            api_key: Optional API key for server-side processing
            api_url: Optional API URL

        Returns:
            AsyncSentienceBrowser instance configured to use the existing context
        """
        instance = cls(api_key=api_key, api_url=api_url)
        instance.context = context
        pages = context.pages
        instance.page = pages[0] if pages else await context.new_page()

        # Apply stealth if available
        if STEALTH_AVAILABLE:
            await stealth_async(instance.page)

        # Wait for extension to be ready
        await asyncio.sleep(0.5)

        return instance

    @classmethod
    async def from_page(
        cls,
        page: AsyncPage,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "AsyncSentienceBrowser":
        """
        Create AsyncSentienceBrowser from an existing Playwright Page.

        Args:
            page: Existing Playwright Page
            api_key: Optional API key for server-side processing
            api_url: Optional API URL

        Returns:
            AsyncSentienceBrowser instance configured to use the existing page
        """
        instance = cls(api_key=api_key, api_url=api_url)
        instance.page = page
        instance.context = page.context

        # Apply stealth if available
        if STEALTH_AVAILABLE:
            await stealth_async(instance.page)

        # Wait for extension to be ready
        await asyncio.sleep(0.5)

        return instance
