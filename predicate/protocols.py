"""
Protocol definitions for testability and dependency injection.

These protocols define the minimal interface required by agent classes,
enabling better testability through mocking while maintaining type safety.
"""

from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import Page

    from .models import Snapshot


@runtime_checkable
class PageProtocol(Protocol):
    """
    Protocol for Playwright Page operations used by agents.

    This protocol defines the minimal interface required from Playwright's Page object.
    Agents use this interface to interact with the browser page.
    """

    @property
    def url(self) -> str:
        """Current page URL."""
        ...

    def evaluate(self, script: str, *args: Any, **kwargs: Any) -> Any:
        """
        Evaluate JavaScript in the page context.

        Args:
            script: JavaScript code to evaluate
            *args: Arguments to pass to the script
            **kwargs: Keyword arguments to pass to the script

        Returns:
            Result of the JavaScript evaluation
        """
        ...

    def goto(self, url: str, **kwargs: Any) -> Any | None:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            **kwargs: Additional navigation options

        Returns:
            Response object or None
        """
        ...

    def wait_for_timeout(self, timeout: int) -> None:
        """
        Wait for a specified timeout.

        Args:
            timeout: Timeout in milliseconds
        """
        ...

    def wait_for_load_state(self, state: str = "load", timeout: int | None = None) -> None:
        """
        Wait for page load state.

        Args:
            state: Load state to wait for (e.g., "load", "domcontentloaded", "networkidle")
            timeout: Optional timeout in milliseconds
        """
        ...


@runtime_checkable
class BrowserProtocol(Protocol):
    """
    Protocol for browser operations used by agents.

    This protocol defines the minimal interface required from SentienceBrowser.
    Agents use this interface to interact with the browser and take snapshots.

    Note: SentienceBrowser naturally implements this protocol, so no changes
    are required to existing code. This protocol enables better testability
    through mocking.
    """

    @property
    def page(self) -> PageProtocol | None:
        """
        Current Playwright Page object.

        Returns:
            Page object if browser is started, None otherwise
        """
        ...

    def start(self) -> None:
        """Start the browser session."""
        ...

    def close(self, output_path: str | None = None) -> str | None:
        """
        Close the browser session.

        Args:
            output_path: Optional path to save browser state/output

        Returns:
            Path to saved output or None
        """
        ...

    def goto(self, url: str) -> None:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
        """
        ...


@runtime_checkable
class AsyncPageProtocol(Protocol):
    """
    Protocol for async Playwright Page operations.

    Similar to PageProtocol but for async operations.
    """

    @property
    def url(self) -> str:
        """Current page URL."""
        ...

    async def evaluate(self, script: str, *args: Any, **kwargs: Any) -> Any:
        """
        Evaluate JavaScript in the page context (async).

        Args:
            script: JavaScript code to evaluate
            *args: Arguments to pass to the script
            **kwargs: Keyword arguments to pass to the script

        Returns:
            Result of the JavaScript evaluation
        """
        ...

    async def goto(self, url: str, **kwargs: Any) -> Any | None:
        """
        Navigate to a URL (async).

        Args:
            url: URL to navigate to
            **kwargs: Additional navigation options

        Returns:
            Response object or None
        """
        ...

    async def wait_for_timeout(self, timeout: int) -> None:
        """
        Wait for a specified timeout (async).

        Args:
            timeout: Timeout in milliseconds
        """
        ...

    async def wait_for_load_state(self, state: str = "load", timeout: int | None = None) -> None:
        """
        Wait for page load state (async).

        Args:
            state: Load state to wait for (e.g., "load", "domcontentloaded", "networkidle")
            timeout: Optional timeout in milliseconds
        """
        ...


@runtime_checkable
class AsyncBrowserProtocol(Protocol):
    """
    Protocol for async browser operations.

    Similar to BrowserProtocol but for async operations.
    """

    @property
    def page(self) -> AsyncPageProtocol | None:
        """
        Current Playwright AsyncPage object.

        Returns:
            AsyncPage object if browser is started, None otherwise
        """
        ...

    async def start(self) -> None:
        """Start the browser session (async)."""
        ...

    async def close(self, output_path: str | None = None) -> str | None:
        """
        Close the browser session (async).

        Args:
            output_path: Optional path to save browser state/output

        Returns:
            Path to saved output or None
        """
        ...

    async def goto(self, url: str) -> None:
        """
        Navigate to a URL (async).

        Args:
            url: URL to navigate to
        """
        ...
