"""
Expect/Assert functionality
"""

import asyncio
import time

from .browser import AsyncSentienceBrowser, SentienceBrowser
from .models import Element
from .query import query
from .wait import wait_for, wait_for_async


class Expectation:
    """Assertion helper for element expectations"""

    def __init__(self, browser: SentienceBrowser, selector: str | dict):
        self.browser = browser
        self.selector = selector

    def to_be_visible(self, timeout: float = 10.0) -> Element:
        """Assert element is visible (exists and in viewport)"""
        result = wait_for(self.browser, self.selector, timeout=timeout)

        if not result.found:
            raise AssertionError(f"Element not found: {self.selector} (timeout: {timeout}s)")

        element = result.element
        if not element.in_viewport:
            raise AssertionError(f"Element found but not visible in viewport: {self.selector}")

        return element

    def to_exist(self, timeout: float = 10.0) -> Element:
        """Assert element exists"""
        result = wait_for(self.browser, self.selector, timeout=timeout)

        if not result.found:
            raise AssertionError(f"Element does not exist: {self.selector} (timeout: {timeout}s)")

        return result.element

    def to_have_text(self, expected_text: str, timeout: float = 10.0) -> Element:
        """Assert element has specific text"""
        result = wait_for(self.browser, self.selector, timeout=timeout)

        if not result.found:
            raise AssertionError(f"Element not found: {self.selector} (timeout: {timeout}s)")

        element = result.element
        if not element.text or expected_text not in element.text:
            raise AssertionError(
                f"Element text mismatch. Expected '{expected_text}', got '{element.text}'"
            )

        return element

    def to_have_count(self, expected_count: int, timeout: float = 10.0) -> None:
        """Assert selector matches exactly N elements"""
        from .snapshot import snapshot

        start_time = time.time()
        while time.time() - start_time < timeout:
            snap = snapshot(self.browser)
            matches = query(snap, self.selector)

            if len(matches) == expected_count:
                return

            time.sleep(0.25)

        # Final check
        snap = snapshot(self.browser)
        matches = query(snap, self.selector)
        actual_count = len(matches)

        raise AssertionError(
            f"Element count mismatch. Expected {expected_count}, got {actual_count}"
        )


def expect(browser: SentienceBrowser, selector: str | dict) -> Expectation:
    """
    Create expectation helper for assertions

    Args:
        browser: SentienceBrowser instance
        selector: String DSL or dict query

    Returns:
        Expectation helper
    """
    return Expectation(browser, selector)


class ExpectationAsync:
    """Assertion helper for element expectations (async)"""

    def __init__(self, browser: AsyncSentienceBrowser, selector: str | dict):
        self.browser = browser
        self.selector = selector

    async def to_be_visible(self, timeout: float = 10.0) -> Element:
        """Assert element is visible (exists and in viewport)"""
        result = await wait_for_async(self.browser, self.selector, timeout=timeout)

        if not result.found:
            raise AssertionError(f"Element not found: {self.selector} (timeout: {timeout}s)")

        element = result.element
        if not element.in_viewport:
            raise AssertionError(f"Element found but not visible in viewport: {self.selector}")

        return element

    async def to_exist(self, timeout: float = 10.0) -> Element:
        """Assert element exists"""
        result = await wait_for_async(self.browser, self.selector, timeout=timeout)

        if not result.found:
            raise AssertionError(f"Element does not exist: {self.selector} (timeout: {timeout}s)")

        return result.element

    async def to_have_text(self, expected_text: str, timeout: float = 10.0) -> Element:
        """Assert element has specific text"""
        result = await wait_for_async(self.browser, self.selector, timeout=timeout)

        if not result.found:
            raise AssertionError(f"Element not found: {self.selector} (timeout: {timeout}s)")

        element = result.element
        if not element.text or expected_text not in element.text:
            raise AssertionError(
                f"Element text mismatch. Expected '{expected_text}', got '{element.text}'"
            )

        return element

    async def to_have_count(self, expected_count: int, timeout: float = 10.0) -> None:
        """Assert selector matches exactly N elements"""
        from .snapshot import snapshot_async

        start_time = time.time()
        while time.time() - start_time < timeout:
            snap = await snapshot_async(self.browser)
            matches = query(snap, self.selector)

            if len(matches) == expected_count:
                return

            await asyncio.sleep(0.25)

        # Final check
        snap = await snapshot_async(self.browser)
        matches = query(snap, self.selector)
        actual_count = len(matches)

        raise AssertionError(
            f"Element count mismatch. Expected {expected_count}, got {actual_count}"
        )


def expect_async(browser: AsyncSentienceBrowser, selector: str | dict) -> ExpectationAsync:
    """
    Create expectation helper for assertions (async)

    Args:
        browser: AsyncSentienceBrowser instance
        selector: String DSL or dict query

    Returns:
        ExpectationAsync helper

    Example:
        # Assert element is visible
        element = await expect_async(browser, "role=button").to_be_visible()

        # Assert element has text
        element = await expect_async(browser, "h1").to_have_text("Welcome")

        # Assert element exists
        element = await expect_async(browser, "role=link").to_exist()

        # Assert count
        await expect_async(browser, "role=button").to_have_count(5)
    """
    return ExpectationAsync(browser, selector)
