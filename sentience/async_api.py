"""
Async API for Sentience SDK - Use this in asyncio contexts

This module provides async versions of all Sentience SDK functions.
Use AsyncSentienceBrowser when working with async/await code.
"""

import asyncio
import base64
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from sentience._extension_loader import find_extension_path
from sentience.models import (
    ActionResult,
    BBox,
    Element,
    ProxyConfig,
    Snapshot,
    SnapshotOptions,
    StorageState,
    WaitResult,
)

# Import stealth for bot evasion (optional - graceful fallback if not available)
try:
    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False


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
        viewport: dict[str, int] | None = None,
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
            viewport: Optional viewport size as dict with 'width' and 'height' keys.
                     Defaults to {"width": 1280, "height": 800}
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

        # Viewport configuration
        self.viewport = viewport or {"width": 1280, "height": 800}

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
            "viewport": self.viewport,
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

    async def _inject_storage_state(
        self, storage_state: str | Path | StorageState | dict
    ) -> None:
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
        context: BrowserContext,
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
        page: Page,
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


# ========== Async Snapshot Functions ==========


async def snapshot(
    browser: AsyncSentienceBrowser,
    options: SnapshotOptions | None = None,
) -> Snapshot:
    """
    Take a snapshot of the current page (async)

    Args:
        browser: AsyncSentienceBrowser instance
        options: Snapshot options (screenshot, limit, filter, etc.)
                If None, uses default options.

    Returns:
        Snapshot object

    Example:
        # Basic snapshot with defaults
        snap = await snapshot(browser)

        # With options
        snap = await snapshot(browser, SnapshotOptions(
            screenshot=True,
            limit=100,
            show_overlay=True
        ))
    """
    # Use default options if none provided
    if options is None:
        options = SnapshotOptions()

    # Determine if we should use server-side API
    should_use_api = (
        options.use_api if options.use_api is not None else (browser.api_key is not None)
    )

    if should_use_api and browser.api_key:
        # Use server-side API (Pro/Enterprise tier)
        return await _snapshot_via_api(browser, options)
    else:
        # Use local extension (Free tier)
        return await _snapshot_via_extension(browser, options)


async def _snapshot_via_extension(
    browser: AsyncSentienceBrowser,
    options: SnapshotOptions,
) -> Snapshot:
    """Take snapshot using local extension (Free tier) - async"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    # Wait for extension injection to complete
    try:
        await browser.page.wait_for_function(
            "typeof window.sentience !== 'undefined'",
            timeout=5000,
        )
    except Exception as e:
        try:
            diag = await browser.page.evaluate(
                """() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })"""
            )
        except Exception:
            diag = {"error": "Could not gather diagnostics"}

        raise RuntimeError(
            f"Sentience extension failed to inject window.sentience API. "
            f"Is the extension loaded? Diagnostics: {diag}"
        ) from e

    # Build options dict for extension API
    ext_options: dict[str, Any] = {}
    if options.screenshot is not False:
        ext_options["screenshot"] = options.screenshot
    if options.limit != 50:
        ext_options["limit"] = options.limit
    if options.filter is not None:
        ext_options["filter"] = (
            options.filter.model_dump() if hasattr(options.filter, "model_dump") else options.filter
        )

    # Call extension API
    result = await browser.page.evaluate(
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        ext_options,
    )

    # Save trace if requested
    if options.save_trace:
        from sentience.snapshot import _save_trace_to_file

        _save_trace_to_file(result.get("raw_elements", []), options.trace_path)

    # Show visual overlay if requested
    if options.show_overlay:
        raw_elements = result.get("raw_elements", [])
        if raw_elements:
            await browser.page.evaluate(
                """
                (elements) => {
                    if (window.sentience && window.sentience.showOverlay) {
                        window.sentience.showOverlay(elements, null);
                    }
                }
                """,
                raw_elements,
            )

    # Validate and parse with Pydantic
    snapshot_obj = Snapshot(**result)
    return snapshot_obj


async def _snapshot_via_api(
    browser: AsyncSentienceBrowser,
    options: SnapshotOptions,
) -> Snapshot:
    """Take snapshot using server-side API (Pro/Enterprise tier) - async"""
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    if not browser.api_key:
        raise ValueError("API key required for server-side processing")

    if not browser.api_url:
        raise ValueError("API URL required for server-side processing")

    # Wait for extension injection
    try:
        await browser.page.wait_for_function("typeof window.sentience !== 'undefined'", timeout=5000)
    except Exception as e:
        raise RuntimeError(
            "Sentience extension failed to inject. Cannot collect raw data for API processing."
        ) from e

    # Step 1: Get raw data from local extension
    raw_options: dict[str, any] = {}
    if options.screenshot is not False:
        raw_options["screenshot"] = options.screenshot

    raw_result = await browser.page.evaluate(
        """
        (options) => {
            return window.sentience.snapshot(options);
        }
        """,
        raw_options,
    )

    # Save trace if requested
    if options.save_trace:
        from sentience.snapshot import _save_trace_to_file

        _save_trace_to_file(raw_result.get("raw_elements", []), options.trace_path)

    # Step 2: Send to server for smart ranking/filtering
    import json

    from sentience.snapshot import MAX_PAYLOAD_BYTES

    payload = {
        "raw_elements": raw_result.get("raw_elements", []),
        "url": raw_result.get("url", ""),
        "viewport": raw_result.get("viewport"),
        "goal": options.goal,
        "options": {
            "limit": options.limit,
            "filter": options.filter.model_dump() if options.filter else None,
        },
    }

    # Check payload size
    payload_json = json.dumps(payload)
    payload_size = len(payload_json.encode("utf-8"))
    if payload_size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Payload size ({payload_size / 1024 / 1024:.2f}MB) exceeds server limit "
            f"({MAX_PAYLOAD_BYTES / 1024 / 1024:.0f}MB). "
            f"Try reducing the number of elements on the page or filtering elements."
        )

    headers = {
        "Authorization": f"Bearer {browser.api_key}",
        "Content-Type": "application/json",
    }

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{browser.api_url}/v1/snapshot",
                data=payload_json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                api_result = await response.json()

        # Merge API result with local data
        snapshot_data = {
            "status": api_result.get("status", "success"),
            "timestamp": api_result.get("timestamp"),
            "url": api_result.get("url", raw_result.get("url", "")),
            "viewport": api_result.get("viewport", raw_result.get("viewport")),
            "elements": api_result.get("elements", []),
            "screenshot": raw_result.get("screenshot"),
            "screenshot_format": raw_result.get("screenshot_format"),
            "error": api_result.get("error"),
        }

        # Show visual overlay if requested
        if options.show_overlay:
            elements = api_result.get("elements", [])
            if elements:
                await browser.page.evaluate(
                    """
                    (elements) => {
                        if (window.sentience && window.sentience.showOverlay) {
                            window.sentience.showOverlay(elements, null);
                        }
                    }
                    """,
                    elements,
                )

        return Snapshot(**snapshot_data)
    except ImportError:
        # Fallback to requests if aiohttp not available (shouldn't happen in async context)
        raise RuntimeError(
            "aiohttp is required for async API calls. Install it with: pip install aiohttp"
        )
    except Exception as e:
        raise RuntimeError(f"API request failed: {e}")


# ========== Async Action Functions ==========


async def click(
    browser: AsyncSentienceBrowser,
    element_id: int,
    use_mouse: bool = True,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Click an element by ID using hybrid approach (async)

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot
        use_mouse: If True, use Playwright's mouse.click() at element center
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    if use_mouse:
        try:
            snap = await snapshot(browser)
            element = None
            for el in snap.elements:
                if el.id == element_id:
                    element = el
                    break

            if element:
                center_x = element.bbox.x + element.bbox.width / 2
                center_y = element.bbox.y + element.bbox.height / 2
                try:
                    await browser.page.mouse.click(center_x, center_y)
                    success = True
                except Exception:
                    success = True
            else:
                try:
                    success = await browser.page.evaluate(
                        """
                        (id) => {
                            return window.sentience.click(id);
                        }
                        """,
                        element_id,
                    )
                except Exception:
                    success = True
        except Exception:
            try:
                success = await browser.page.evaluate(
                    """
                    (id) => {
                        return window.sentience.click(id);
                    }
                    """,
                    element_id,
                )
            except Exception:
                success = True
    else:
        success = await browser.page.evaluate(
            """
            (id) => {
                return window.sentience.click(id);
            }
            """,
            element_id,
        )

    # Wait a bit for navigation/DOM updates
    try:
        await browser.page.wait_for_timeout(500)
    except Exception:
        pass

    duration_ms = int((time.time() - start_time) * 1000)

    # Check if URL changed
    try:
        url_after = browser.page.url
        url_changed = url_before != url_after
    except Exception:
        url_after = url_before
        url_changed = True

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        try:
            snapshot_after = await snapshot(browser)
        except Exception:
            pass

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": "Element not found or not clickable",
            }
        ),
    )


async def type_text(
    browser: AsyncSentienceBrowser, element_id: int, text: str, take_snapshot: bool = False
) -> ActionResult:
    """
    Type text into an element (async)

    Args:
        browser: AsyncSentienceBrowser instance
        element_id: Element ID from snapshot
        text: Text to type
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Focus element first
    focused = await browser.page.evaluate(
        """
        (id) => {
            const el = window.sentience_registry[id];
            if (el) {
                el.focus();
                return true;
            }
            return false;
        }
        """,
        element_id,
    )

    if not focused:
        return ActionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            outcome="error",
            error={"code": "focus_failed", "reason": "Element not found"},
        )

    # Type using Playwright keyboard
    await browser.page.keyboard.type(text)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def press(browser: AsyncSentienceBrowser, key: str, take_snapshot: bool = False) -> ActionResult:
    """
    Press a keyboard key (async)

    Args:
        browser: AsyncSentienceBrowser instance
        key: Key to press (e.g., "Enter", "Escape", "Tab")
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    start_time = time.time()
    url_before = browser.page.url

    # Press key using Playwright
    await browser.page.keyboard.press(key)

    # Wait a bit for navigation/DOM updates
    await browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    outcome = "navigated" if url_changed else "dom_updated"

    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot(browser)

    return ActionResult(
        success=True,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
    )


async def _highlight_rect(
    browser: AsyncSentienceBrowser, rect: dict[str, float], duration_sec: float = 2.0
) -> None:
    """Highlight a rectangle with a red border overlay (async)"""
    if not browser.page:
        return

    highlight_id = f"sentience_highlight_{int(time.time() * 1000)}"

    args = {
        "rect": {
            "x": rect["x"],
            "y": rect["y"],
            "w": rect["w"],
            "h": rect["h"],
        },
        "highlightId": highlight_id,
        "durationSec": duration_sec,
    }

    await browser.page.evaluate(
        """
        (args) => {
            const { rect, highlightId, durationSec } = args;
            const overlay = document.createElement('div');
            overlay.id = highlightId;
            overlay.style.position = 'fixed';
            overlay.style.left = `${rect.x}px`;
            overlay.style.top = `${rect.y}px`;
            overlay.style.width = `${rect.w}px`;
            overlay.style.height = `${rect.h}px`;
            overlay.style.border = '3px solid red';
            overlay.style.borderRadius = '2px';
            overlay.style.boxSizing = 'border-box';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '999999';
            overlay.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
            overlay.style.transition = 'opacity 0.3s ease-out';

            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    if (overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300);
            }, durationSec * 1000);
        }
        """,
        args,
    )


async def click_rect(
    browser: AsyncSentienceBrowser,
    rect: dict[str, float] | BBox,
    highlight: bool = True,
    highlight_duration: float = 2.0,
    take_snapshot: bool = False,
) -> ActionResult:
    """
    Click at the center of a rectangle (async)

    Args:
        browser: AsyncSentienceBrowser instance
        rect: Dictionary with x, y, width (w), height (h) keys, or BBox object
        highlight: Whether to show a red border highlight when clicking
        highlight_duration: How long to show the highlight in seconds
        take_snapshot: Whether to take snapshot after action

    Returns:
        ActionResult
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    # Handle BBox object or dict
    if isinstance(rect, BBox):
        x = rect.x
        y = rect.y
        w = rect.width
        h = rect.height
    else:
        x = rect.get("x", 0)
        y = rect.get("y", 0)
        w = rect.get("w") or rect.get("width", 0)
        h = rect.get("h") or rect.get("height", 0)

    if w <= 0 or h <= 0:
        return ActionResult(
            success=False,
            duration_ms=0,
            outcome="error",
            error={
                "code": "invalid_rect",
                "reason": "Rectangle width and height must be positive",
            },
        )

    start_time = time.time()
    url_before = browser.page.url

    # Calculate center of rectangle
    center_x = x + w / 2
    center_y = y + h / 2

    # Show highlight before clicking
    if highlight:
        await _highlight_rect(browser, {"x": x, "y": y, "w": w, "h": h}, highlight_duration)
        await browser.page.wait_for_timeout(50)

    # Use Playwright's native mouse click
    try:
        await browser.page.mouse.click(center_x, center_y)
        success = True
    except Exception as e:
        success = False
        error_msg = str(e)

    # Wait a bit for navigation/DOM updates
    await browser.page.wait_for_timeout(500)

    duration_ms = int((time.time() - start_time) * 1000)
    url_after = browser.page.url
    url_changed = url_before != url_after

    # Determine outcome
    outcome: str | None = None
    if url_changed:
        outcome = "navigated"
    elif success:
        outcome = "dom_updated"
    else:
        outcome = "error"

    # Optional snapshot after
    snapshot_after: Snapshot | None = None
    if take_snapshot:
        snapshot_after = await snapshot(browser)

    return ActionResult(
        success=success,
        duration_ms=duration_ms,
        outcome=outcome,
        url_changed=url_changed,
        snapshot_after=snapshot_after,
        error=(
            None
            if success
            else {
                "code": "click_failed",
                "reason": error_msg if not success else "Click failed",
            }
        ),
    )


# ========== Re-export Query Functions (Pure Functions - No Async Needed) ==========

# Query functions (find, query) are pure functions that work with Snapshot objects
# They don't need async versions, but we re-export them for convenience
from sentience.query import find, query

__all__ = [
    "AsyncSentienceBrowser",
    "snapshot",
    "click",
    "type_text",
    "press",
    "click_rect",
    "find",
    "query",
]
