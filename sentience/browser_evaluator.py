"""
Browser evaluation helper for common window.sentience API patterns.

Consolidates repeated patterns for:
- Waiting for extension injection
- Calling window.sentience methods
- Error handling with diagnostics
"""

from typing import Any, Optional, Union

from playwright.async_api import Page as AsyncPage
from playwright.sync_api import Page

from .browser import AsyncSentienceBrowser, SentienceBrowser


class BrowserEvaluator:
    """Helper class for common browser evaluation patterns"""

    @staticmethod
    def wait_for_extension(
        page: Union[Page, AsyncPage],
        timeout_ms: int = 5000,
    ) -> None:
        """
        Wait for window.sentience API to be available.

        Args:
            page: Playwright Page instance (sync or async)
            timeout_ms: Timeout in milliseconds (default: 5000)

        Raises:
            RuntimeError: If extension fails to inject within timeout
        """
        if hasattr(page, "wait_for_function"):
            # Sync page
            try:
                page.wait_for_function(
                    "typeof window.sentience !== 'undefined'",
                    timeout=timeout_ms,
                )
            except Exception as e:
                diag = BrowserEvaluator._gather_diagnostics(page)
                raise RuntimeError(
                    f"Sentience extension failed to inject window.sentience API. "
                    f"Is the extension loaded? Diagnostics: {diag}"
                ) from e
        else:
            # Async page - should use async version
            raise TypeError("Use wait_for_extension_async for async pages")

    @staticmethod
    async def wait_for_extension_async(
        page: AsyncPage,
        timeout_ms: int = 5000,
    ) -> None:
        """
        Wait for window.sentience API to be available (async).

        Args:
            page: Playwright AsyncPage instance
            timeout_ms: Timeout in milliseconds (default: 5000)

        Raises:
            RuntimeError: If extension fails to inject within timeout
        """
        try:
            await page.wait_for_function(
                "typeof window.sentience !== 'undefined'",
                timeout=timeout_ms,
            )
        except Exception as e:
            diag = await BrowserEvaluator._gather_diagnostics_async(page)
            raise RuntimeError(
                f"Sentience extension failed to inject window.sentience API. "
                f"Is the extension loaded? Diagnostics: {diag}"
            ) from e

    @staticmethod
    def _gather_diagnostics(page: Union[Page, AsyncPage]) -> dict[str, Any]:
        """
        Gather diagnostics about extension state.

        Args:
            page: Playwright Page instance

        Returns:
            Dictionary with diagnostic information
        """
        try:
            if hasattr(page, "evaluate"):
                # Sync page
                return page.evaluate(
                    """() => ({
                        sentience_defined: typeof window.sentience !== 'undefined',
                        extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                        url: window.location.href
                    })"""
                )
            else:
                return {"error": "Could not gather diagnostics - invalid page type"}
        except Exception:
            return {"error": "Could not gather diagnostics"}

    @staticmethod
    async def _gather_diagnostics_async(page: AsyncPage) -> dict[str, Any]:
        """
        Gather diagnostics about extension state (async).

        Args:
            page: Playwright AsyncPage instance

        Returns:
            Dictionary with diagnostic information
        """
        try:
            return await page.evaluate(
                """() => ({
                    sentience_defined: typeof window.sentience !== 'undefined',
                    extension_id: document.documentElement.dataset.sentienceExtensionId || 'not set',
                    url: window.location.href
                })"""
            )
        except Exception:
            return {"error": "Could not gather diagnostics"}

    @staticmethod
    def call_sentience_method(
        page: Page,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Call a window.sentience method with error handling.

        Args:
            page: Playwright Page instance (sync)
            method_name: Name of the method (e.g., "snapshot", "click")
            *args: Positional arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method

        Returns:
            Result from the method call

        Raises:
            RuntimeError: If method is not available or call fails
        """
        # Build JavaScript call
        if args and kwargs:
            # Both args and kwargs - use object spread
            js_code = f"""
            (args, kwargs) => {{
                return window.sentience.{method_name}(...args, kwargs);
            }}
            """
            result = page.evaluate(js_code, list(args), kwargs)
        elif args:
            # Only args
            js_code = f"""
            (args) => {{
                return window.sentience.{method_name}(...args);
            }}
            """
            result = page.evaluate(js_code, list(args))
        elif kwargs:
            # Only kwargs - pass as single object
            js_code = f"""
            (options) => {{
                return window.sentience.{method_name}(options);
            }}
            """
            result = page.evaluate(js_code, kwargs)
        else:
            # No arguments
            js_code = f"""
            () => {{
                return window.sentience.{method_name}();
            }}
            """
            result = page.evaluate(js_code)

        return result

    @staticmethod
    async def call_sentience_method_async(
        page: AsyncPage,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Call a window.sentience method with error handling (async).

        Args:
            page: Playwright AsyncPage instance
            method_name: Name of the method (e.g., "snapshot", "click")
            *args: Positional arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method

        Returns:
            Result from the method call

        Raises:
            RuntimeError: If method is not available or call fails
        """
        # Build JavaScript call
        if args and kwargs:
            js_code = f"""
            (args, kwargs) => {{
                return window.sentience.{method_name}(...args, kwargs);
            }}
            """
            result = await page.evaluate(js_code, list(args), kwargs)
        elif args:
            js_code = f"""
            (args) => {{
                return window.sentience.{method_name}(...args);
            }}
            """
            result = await page.evaluate(js_code, list(args))
        elif kwargs:
            js_code = f"""
            (options) => {{
                return window.sentience.{method_name}(options);
            }}
            """
            result = await page.evaluate(js_code, kwargs)
        else:
            js_code = f"""
            () => {{
                return window.sentience.{method_name}();
            }}
            """
            result = await page.evaluate(js_code)

        return result

    @staticmethod
    def verify_method_exists(
        page: Page,
        method_name: str,
    ) -> bool:
        """
        Verify that a window.sentience method exists.

        Args:
            page: Playwright Page instance (sync)
            method_name: Name of the method to check

        Returns:
            True if method exists, False otherwise
        """
        try:
            return page.evaluate(f"typeof window.sentience.{method_name} !== 'undefined'")
        except Exception:
            return False

    @staticmethod
    async def verify_method_exists_async(
        page: AsyncPage,
        method_name: str,
    ) -> bool:
        """
        Verify that a window.sentience method exists (async).

        Args:
            page: Playwright AsyncPage instance
            method_name: Name of the method to check

        Returns:
            True if method exists, False otherwise
        """
        try:
            return await page.evaluate(f"typeof window.sentience.{method_name} !== 'undefined'")
        except Exception:
            return False

