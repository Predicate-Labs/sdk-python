"""
Playwright browser harness with extension loading
"""

import asyncio
import logging
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from playwright.async_api import BrowserContext as AsyncBrowserContext
from playwright.async_api import Page as AsyncPage
from playwright.async_api import Playwright as AsyncPlaywright
from playwright.async_api import async_playwright
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from predicate._extension_loader import find_extension_path
from predicate.constants import PREDICATE_API_URL
from predicate.models import ProxyConfig, StorageState, Viewport
from predicate.permissions import PermissionPolicy

logger = logging.getLogger(__name__)

# Import stealth for bot evasion (optional - graceful fallback if not available)
try:
    from playwright_stealth import stealth_async, stealth_sync

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False


def _normalize_domain(domain: str) -> str:
    raw = domain.strip()
    if "://" in raw:
        host = urlparse(raw).hostname or ""
    else:
        host = raw.split("/", 1)[0]
    host = host.split(":", 1)[0]
    return host.strip().lower().lstrip(".")


def _domain_matches(host: str, pattern: str) -> bool:
    host_norm = _normalize_domain(host)
    pat = _normalize_domain(pattern)
    if pat.startswith("*."):
        pat = pat[2:]
    return host_norm == pat or host_norm.endswith(f".{pat}")


def _extract_host(url: str) -> str | None:
    raw = url.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    return parsed.hostname


def _is_domain_allowed(
    host: str | None, allowed: list[str] | None, prohibited: list[str] | None
) -> bool:
    """
    Return True if host is allowed based on allow/deny lists.

    Deny list takes precedence. Empty allow list means allow all.
    """
    if not host:
        return False
    if prohibited:
        for pattern in prohibited:
            if _domain_matches(host, pattern):
                return False
    if allowed:
        return any(_domain_matches(host, pattern) for pattern in allowed)
    return True


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
        device_scale_factor: float | None = None,
        allowed_domains: list[str] | None = None,
        prohibited_domains: list[str] | None = None,
        keep_alive: bool = False,
        permission_policy: PermissionPolicy | dict | None = None,
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
            permission_policy: Optional permission policy to apply on context creation.
        """
        self.api_key = api_key
        # Only set api_url if api_key is provided, otherwise None (free tier)
        # Defaults to production API if key is present but url is missing
        if self.api_key and not api_url:
            self.api_url = PREDICATE_API_URL
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

        # Domain policies + keep-alive
        self.allowed_domains = allowed_domains or []
        self.prohibited_domains = prohibited_domains or []
        self.keep_alive = keep_alive
        self.permission_policy = self._coerce_permission_policy(permission_policy)

        # Viewport configuration - convert dict to Viewport if needed
        if viewport is None:
            self.viewport = Viewport(width=1280, height=800)
        elif isinstance(viewport, dict):
            self.viewport = Viewport(width=viewport["width"], height=viewport["height"])
        else:
            self.viewport = viewport

        # Device scale factor for high-DPI emulation
        self.device_scale_factor = device_scale_factor

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
                logger.warning(
                    f"Unsupported proxy scheme: {parsed.scheme}. Supported: http, https, socks5"
                )
                return None

            # Validate host and port
            if not parsed.hostname or not parsed.port:
                logger.warning(
                    "Proxy URL must include hostname and port. Expected format: http://username:password@host:port"
                )
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
            logger.warning(
                f"Invalid proxy configuration: {e}. Expected format: http://username:password@host:port"
            )
            return None

    def _coerce_permission_policy(
        self, policy: PermissionPolicy | dict | None
    ) -> PermissionPolicy | None:
        if policy is None:
            return None
        if isinstance(policy, PermissionPolicy):
            return policy
        if isinstance(policy, dict):
            return PermissionPolicy(**policy)
        raise TypeError("permission_policy must be PermissionPolicy, dict, or None")

    def apply_permission_policy(self, context: BrowserContext) -> None:
        policy = self.permission_policy
        if policy is None:
            return
        if policy.default in ("clear", "deny"):
            context.clear_permissions()
        if policy.geolocation:
            context.set_geolocation(policy.geolocation)
        if policy.auto_grant:
            context.grant_permissions(policy.auto_grant, origin=policy.origin)

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
            "--disable-infobars",
            # WebRTC leak protection (prevents real IP exposure when using proxies/VPNs)
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ]

        # Only add --no-sandbox on Linux (causes crashes on macOS)
        # macOS sandboxing works fine and the flag actually causes crashes
        if platform.system() == "Linux":
            args.append("--no-sandbox")

        # Add GPU-disabling flags for macOS to prevent Chrome for Testing crash-on-exit
        # These flags help avoid EXC_BAD_ACCESS crashes during browser shutdown
        if platform.system() == "Darwin":  # macOS
            args.extend(
                [
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                    "--disable-breakpad",  # Disable crash reporter to prevent macOS crash dialogs
                    "--disable-crash-reporter",  # Disable crash reporter UI
                    "--disable-crash-handler",  # Disable crash handler completely
                    "--disable-in-process-stack-traces",  # Disable stack trace collection
                    "--disable-hang-monitor",  # Disable hang detection
                    "--disable-background-networking",  # Disable background networking
                    "--disable-background-timer-throttling",  # Disable background throttling
                    "--disable-backgrounding-occluded-windows",  # Disable backgrounding
                    "--disable-renderer-backgrounding",  # Disable renderer backgrounding
                    "--disable-features=TranslateUI",  # Disable translate UI
                    "--disable-ipc-flooding-protection",  # Disable IPC flooding protection
                    "--disable-logging",  # Disable logging to reduce stderr noise
                    "--log-level=3",  # Set log level to fatal only (suppresses warnings)
                ]
            )

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
            # Note: Don't set "channel" - let Playwright use its default managed Chromium
            # Setting channel=None doesn't force bundled Chromium and can still pick Chrome for Testing
        }

        # Add device scale factor if configured
        if self.device_scale_factor is not None:
            launch_params["device_scale_factor"] = self.device_scale_factor

        # Add proxy if configured
        if proxy_config:
            launch_params["proxy"] = proxy_config.to_playwright_dict()
            # Ignore HTTPS errors when using proxy (many residential proxies use self-signed certs)
            launch_params["ignore_https_errors"] = True
            logger.info(f"Using proxy: {proxy_config.server}")

        # Add video recording if configured
        if self.record_video_dir:
            video_dir = Path(self.record_video_dir)
            video_dir.mkdir(parents=True, exist_ok=True)
            launch_params["record_video_dir"] = str(video_dir)
            launch_params["record_video_size"] = self.record_video_size
            logger.info(
                f"Recording video to: {video_dir} (Resolution: {self.record_video_size['width']}x{self.record_video_size['height']})"
            )

        # Launch persistent context (required for extensions)
        # Note: We pass headless=False to launch_persistent_context because we handle
        # headless mode via the --headless=new arg above. This is a Playwright workaround.
        self.context = self.playwright.chromium.launch_persistent_context(**launch_params)

        if self.context is not None:
            self.apply_permission_policy(self.context)

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
        """Navigate to a URL and ensure extension is ready.

        This enforces domain allow/deny policies. Direct page.goto() calls
        bypass policy checks.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")
        host = _extract_host(url)
        if not _is_domain_allowed(host, self.allowed_domains, self.prohibited_domains):
            raise ValueError(f"domain not allowed: {host}")

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
            logger.debug(f"Injected {len(state.cookies)} cookie(s)")

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
                        logger.debug(
                            f"Injected {len(origin_data.localStorage)} localStorage item(s) for {origin}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to inject localStorage for {origin}: {e}")

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
            If keep_alive is True, returns None and skips shutdown.
        """
        # CRITICAL: Don't access page.video.path() BEFORE closing context
        # This can poke the video subsystem at an awkward time and cause crashes on macOS
        # Instead, we'll locate the video file after context closes

        if self.keep_alive:
            logger.info("Keep-alive enabled; skipping browser shutdown.")
            return None

        # Close context (this triggers video file finalization)
        if self.context:
            self.context.close()
            # Small grace period to ensure video file is fully flushed to disk
            time.sleep(0.5)

        # Close playwright
        if self.playwright:
            self.playwright.stop()

        # Clean up extension directory
        if self._extension_path and os.path.exists(self._extension_path):
            shutil.rmtree(self._extension_path)

        # NOW resolve video path after context is closed and video is finalized
        temp_video_path = None
        if self.record_video_dir:
            try:
                # Locate the newest .webm file in record_video_dir
                # This avoids touching page.video during teardown
                video_dir = Path(self.record_video_dir)
                if video_dir.exists():
                    webm_files = list(video_dir.glob("*.webm"))
                    if webm_files:
                        # Get the most recently modified file
                        temp_video_path = max(webm_files, key=lambda p: p.stat().st_mtime)
                        logger.debug(f"Found video file: {temp_video_path}")
            except Exception as e:
                logger.warning(f"Could not locate video file: {e}")

        # Rename/move video if output_path is specified
        final_path = str(temp_video_path) if temp_video_path else None
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
                final_path = str(temp_video_path)

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
            from predicate import SentienceBrowser, snapshot

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
            from predicate import SentienceBrowser, snapshot

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
        device_scale_factor: float | None = None,
        executable_path: str | None = None,
        allowed_domains: list[str] | None = None,
        prohibited_domains: list[str] | None = None,
        keep_alive: bool = False,
        permission_policy: PermissionPolicy | dict | None = None,
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
            device_scale_factor: Optional device scale factor to emulate high-DPI (Retina) screens.
                               Examples: 1.0 (default, standard DPI)
                                        2.0 (Retina/high-DPI, like MacBook Pro)
                                        3.0 (very high DPI)
                               If None, defaults to 1.0 (standard DPI).
            executable_path: Optional path to Chromium executable. If provided, forces use of
                            this specific browser binary instead of Playwright's managed browser.
                            Useful to guarantee Chromium (not Chrome for Testing) on macOS.
                            Example: "/path/to/playwright/chromium-1234/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
            permission_policy: Optional permission policy to apply on context creation.
        """
        self.api_key = api_key
        # Only set api_url if api_key is provided, otherwise None (free tier)
        if self.api_key and not api_url:
            self.api_url = PREDICATE_API_URL
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

        # Domain policies + keep-alive
        self.allowed_domains = allowed_domains or []
        self.prohibited_domains = prohibited_domains or []
        self.keep_alive = keep_alive
        self.permission_policy = self._coerce_permission_policy(permission_policy)

        # Viewport configuration - convert dict to Viewport if needed
        if viewport is None:
            self.viewport = Viewport(width=1280, height=800)
        elif isinstance(viewport, dict):
            self.viewport = Viewport(width=viewport["width"], height=viewport["height"])
        else:
            self.viewport = viewport

        # Device scale factor for high-DPI emulation
        self.device_scale_factor = device_scale_factor

        # Executable path override (for forcing specific Chromium binary)
        self.executable_path = executable_path

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
                logger.warning(
                    f"Unsupported proxy scheme: {parsed.scheme}. Supported: http, https, socks5"
                )
                return None

            # Validate host and port
            if not parsed.hostname or not parsed.port:
                logger.warning(
                    "Proxy URL must include hostname and port. Expected format: http://username:password@host:port"
                )
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
            logger.warning(
                f"Invalid proxy configuration: {e}. Expected format: http://username:password@host:port"
            )
            return None

    def _coerce_permission_policy(
        self, policy: PermissionPolicy | dict | None
    ) -> PermissionPolicy | None:
        if policy is None:
            return None
        if isinstance(policy, PermissionPolicy):
            return policy
        if isinstance(policy, dict):
            return PermissionPolicy(**policy)
        raise TypeError("permission_policy must be PermissionPolicy, dict, or None")

    async def apply_permission_policy(self, context: AsyncBrowserContext) -> None:
        policy = self.permission_policy
        if policy is None:
            return
        if policy.default in ("clear", "deny"):
            await context.clear_permissions()
        if policy.geolocation:
            await context.set_geolocation(policy.geolocation)
        if policy.auto_grant:
            await context.grant_permissions(policy.auto_grant, origin=policy.origin)

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
            "--disable-infobars",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        ]

        # Only add --no-sandbox on Linux (causes crashes on macOS)
        # macOS sandboxing works fine and the flag actually causes crashes
        if platform.system() == "Linux":
            args.append("--no-sandbox")

        # Add GPU-disabling flags for macOS to prevent Chrome for Testing crash-on-exit
        # These flags help avoid EXC_BAD_ACCESS crashes during browser shutdown
        if platform.system() == "Darwin":  # macOS
            args.extend(
                [
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                    "--disable-breakpad",  # Disable crash reporter to prevent macOS crash dialogs
                    "--disable-crash-reporter",  # Disable crash reporter UI
                    "--disable-crash-handler",  # Disable crash handler completely
                    "--disable-in-process-stack-traces",  # Disable stack trace collection
                    "--disable-hang-monitor",  # Disable hang detection
                    "--disable-background-networking",  # Disable background networking
                    "--disable-background-timer-throttling",  # Disable background throttling
                    "--disable-backgrounding-occluded-windows",  # Disable backgrounding
                    "--disable-renderer-backgrounding",  # Disable renderer backgrounding
                    "--disable-features=TranslateUI",  # Disable translate UI
                    "--disable-ipc-flooding-protection",  # Disable IPC flooding protection
                    "--disable-logging",  # Disable logging to reduce stderr noise
                    "--log-level=3",  # Set log level to fatal only (suppresses warnings)
                ]
            )

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
            # Note: Don't set "channel" - let Playwright use its default managed Chromium
            # Setting channel=None doesn't force bundled Chromium and can still pick Chrome for Testing
        }

        # If executable_path is provided, use it to force specific Chromium binary
        # This guarantees we use Chromium (not Chrome for Testing) on macOS
        if self.executable_path:
            launch_params["executable_path"] = self.executable_path
            logger.info(f"Using explicit executable: {self.executable_path}")

        # Add device scale factor if configured
        if self.device_scale_factor is not None:
            launch_params["device_scale_factor"] = self.device_scale_factor

        # Add proxy if configured
        if proxy_config:
            launch_params["proxy"] = proxy_config.to_playwright_dict()
            launch_params["ignore_https_errors"] = True
            logger.info(f"Using proxy: {proxy_config.server}")

        # Add video recording if configured
        if self.record_video_dir:
            video_dir = Path(self.record_video_dir)
            video_dir.mkdir(parents=True, exist_ok=True)
            launch_params["record_video_dir"] = str(video_dir)
            launch_params["record_video_size"] = self.record_video_size
            logger.info(
                f"Recording video to: {video_dir} (Resolution: {self.record_video_size['width']}x{self.record_video_size['height']})"
            )

        # Launch persistent context
        self.context = await self.playwright.chromium.launch_persistent_context(**launch_params)

        if self.context is not None:
            await self.apply_permission_policy(self.context)

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
        """Navigate to a URL and ensure extension is ready (async).

        This enforces domain allow/deny policies. Direct page.goto() calls
        bypass policy checks.
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call await start() first.")
        host = _extract_host(url)
        if not _is_domain_allowed(host, self.allowed_domains, self.prohibited_domains):
            raise ValueError(f"domain not allowed: {host}")

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
            logger.debug(f"Injected {len(state.cookies)} cookie(s)")

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
                        logger.debug(
                            f"Injected {len(origin_data.localStorage)} localStorage item(s) for {origin}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to inject localStorage for {origin}: {e}")

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

    async def close(self, output_path: str | Path | None = None) -> tuple[str | None, bool]:
        """
        Close browser and cleanup (async)

        Args:
            output_path: Optional path to rename the video file to

        Returns:
            Tuple of (video_path, shutdown_clean)
            - video_path: Path to video file if recording was enabled, None otherwise
            - shutdown_clean: True if shutdown completed without errors, False if there were issues

        Note: Video path is resolved AFTER context close to avoid touching video
        subsystem during teardown, which can cause crashes on macOS.
        If keep_alive is True, returns (None, True) and skips shutdown.
        """
        if self.keep_alive:
            logger.info("Keep-alive enabled; skipping browser shutdown.")
            return None, True

        # CRITICAL: Don't access page.video.path() BEFORE closing context
        # This can poke the video subsystem at an awkward time and cause crashes
        # Instead, we'll locate the video file after context closes

        # CRITICAL: Wait before closing to ensure all operations are complete
        # This is especially important for video recording - we need to ensure
        # all frames are written and the encoder is ready to finalize
        if platform.system() == "Darwin":  # macOS
            # On macOS, give extra time for video encoder to finish writing frames
            # 4K video recording needs more time to flush buffers
            logger.debug("Waiting for video recording to stabilize before closing (macOS)...")
            await asyncio.sleep(2.0)
        else:
            await asyncio.sleep(1.0)

        # Graceful shutdown: close context first, then playwright
        # Use longer timeouts on macOS where video finalization can take longer
        context_close_success = True
        if self.context:
            try:
                # Give context time to close gracefully (especially for video finalization)
                # Increased timeout for macOS where 4K video finalization can take longer
                await asyncio.wait_for(self.context.close(), timeout=30.0)
                logger.debug("Context closed successfully")
            except TimeoutError:
                logger.warning("Context close timed out, continuing with cleanup...")
                context_close_success = False
            except Exception as e:
                logger.warning(f"Error closing context: {e}")
                context_close_success = False
            finally:
                self.context = None

        # Give Chrome a moment to fully flush video + release resources
        # This avoids stopping the driver while the browser is still finishing the .webm write/encoder shutdown
        # Increased grace period on macOS to allow more time for process cleanup
        grace_period = 2.0 if platform.system() == "Darwin" else 1.0
        await asyncio.sleep(grace_period)

        playwright_stop_success = True
        if self.playwright:
            try:
                # Give playwright time to stop gracefully
                # Increased timeout to match context close timeout
                await asyncio.wait_for(self.playwright.stop(), timeout=15.0)
                logger.debug("Playwright stopped successfully")
            except TimeoutError:
                logger.warning("Playwright stop timed out, continuing with cleanup...")
                playwright_stop_success = False
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
                playwright_stop_success = False
            finally:
                self.playwright = None

        # Additional cleanup: On macOS, wait a bit more to ensure all browser processes are terminated
        # This helps prevent crash dialogs from appearing
        if platform.system() == "Darwin":
            await asyncio.sleep(0.5)

        # NOW resolve video path after context is closed and video is finalized
        temp_video_path = None
        if self.record_video_dir:
            try:
                # Locate the newest .webm file in record_video_dir
                # This avoids touching page.video during teardown
                video_dir = Path(self.record_video_dir)
                if video_dir.exists():
                    webm_files = list(video_dir.glob("*.webm"))
                    if webm_files:
                        # Get the most recently modified file
                        temp_video_path = max(webm_files, key=lambda p: p.stat().st_mtime)
                        logger.debug(f"Found video file: {temp_video_path}")
            except Exception as e:
                logger.warning(f"Could not locate video file: {e}")

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

        # Log shutdown status (useful for detecting crashes in headless mode)
        shutdown_clean = context_close_success and playwright_stop_success
        if not shutdown_clean:
            logger.warning(
                f"Browser shutdown had issues - may indicate a crash "
                f"(context_close: {context_close_success}, playwright_stop: {playwright_stop_success})"
            )
        else:
            logger.debug("Browser shutdown completed cleanly")

        # Return tuple: (video_path, shutdown_clean)
        # This allows callers to detect crashes even in headless mode
        return (final_path, shutdown_clean)

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Ignore return value in context manager exit
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


# -----------------------------------------------------------------------------
# Predicate rebrand aliases
# -----------------------------------------------------------------------------
#
# The TypeScript SDK exposes `PredicateBrowser` as an alias of `SentienceBrowser`.
# For parity (and to make docs/examples clearer), we also expose aliases here.
#
# Keep the Sentience* names for backward compatibility.
PredicateBrowser = SentienceBrowser
AsyncPredicateBrowser = AsyncSentienceBrowser
