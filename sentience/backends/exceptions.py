"""
Custom exceptions for Sentience backends.

These exceptions provide clear, actionable error messages when things go wrong
during browser-use integration or backend operations.
"""

from dataclasses import dataclass
from typing import Any


class SentienceBackendError(Exception):
    """Base exception for all Sentience backend errors."""

    pass


@dataclass
class ExtensionDiagnostics:
    """Diagnostics collected when extension loading fails."""

    sentience_defined: bool = False
    sentience_snapshot: bool = False
    url: str = ""
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtensionDiagnostics":
        """Create from diagnostic dict returned by browser eval."""
        return cls(
            sentience_defined=data.get("sentience_defined", False),
            sentience_snapshot=data.get("sentience_snapshot", False),
            url=data.get("url", ""),
            error=data.get("error"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "sentience_defined": self.sentience_defined,
            "sentience_snapshot": self.sentience_snapshot,
            "url": self.url,
            "error": self.error,
        }


class ExtensionNotLoadedError(SentienceBackendError):
    """
    Raised when the Sentience extension is not loaded in the browser.

    This typically means:
    1. Browser was launched without --load-extension flag
    2. Extension path is incorrect
    3. Extension failed to initialize

    Example fix for browser-use:
        from sentience import get_extension_dir
        from browser_use import BrowserSession, BrowserProfile

        profile = BrowserProfile(
            args=[f"--load-extension={get_extension_dir()}"],
        )
        session = BrowserSession(browser_profile=profile)
    """

    def __init__(
        self,
        message: str,
        timeout_ms: int | None = None,
        diagnostics: ExtensionDiagnostics | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.diagnostics = diagnostics
        super().__init__(message)

    @classmethod
    def from_timeout(
        cls,
        timeout_ms: int,
        diagnostics: ExtensionDiagnostics | None = None,
    ) -> "ExtensionNotLoadedError":
        """Create error from timeout during extension wait."""
        diag_info = ""
        if diagnostics:
            if diagnostics.error:
                diag_info = f"\n  Error: {diagnostics.error}"
            else:
                diag_info = (
                    f"\n  window.sentience defined: {diagnostics.sentience_defined}"
                    f"\n  window.sentience.snapshot available: {diagnostics.sentience_snapshot}"
                    f"\n  Page URL: {diagnostics.url}"
                )

        message = (
            f"Sentience extension not loaded after {timeout_ms}ms.{diag_info}\n\n"
            "To fix this, ensure the extension is loaded when launching the browser:\n\n"
            "  from sentience import get_extension_dir\n"
            "  from browser_use import BrowserSession, BrowserProfile\n\n"
            "  profile = BrowserProfile(\n"
            f'      args=[f"--load-extension={{get_extension_dir()}}"],\n'
            "  )\n"
            "  session = BrowserSession(browser_profile=profile)\n"
        )
        return cls(message, timeout_ms=timeout_ms, diagnostics=diagnostics)


class ExtensionInjectionError(SentienceBackendError):
    """
    Raised when window.sentience API is not available on the page.

    This can happen when:
    1. Page loaded before extension could inject
    2. Page has Content Security Policy blocking extension
    3. Extension crashed or was disabled

    Call snapshot() with a longer timeout or wait for page load.
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
    ) -> None:
        self.url = url
        super().__init__(message)

    @classmethod
    def from_page(cls, url: str) -> "ExtensionInjectionError":
        """Create error for a specific page."""
        message = (
            f"window.sentience API not available on page: {url}\n\n"
            "Possible causes:\n"
            "  1. Page loaded before extension could inject (try increasing timeout)\n"
            "  2. Page has Content Security Policy blocking the extension\n"
            "  3. Extension was disabled or crashed\n\n"
            "Try:\n"
            "  snap = await snapshot(backend, options=SnapshotOptions(timeout_ms=10000))"
        )
        return cls(message, url=url)


class BackendEvalError(SentienceBackendError):
    """
    Raised when JavaScript evaluation fails in the browser.

    This wraps underlying CDP or Playwright errors with context.
    """

    def __init__(
        self,
        message: str,
        expression: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        self.expression = expression
        self.original_error = original_error
        super().__init__(message)


class SnapshotError(SentienceBackendError):
    """
    Raised when taking a snapshot fails.

    This can happen when:
    1. Extension returned null or invalid data
    2. Page is in an invalid state
    3. Extension threw an error
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        raw_result: Any = None,
    ) -> None:
        self.url = url
        self.raw_result = raw_result
        super().__init__(message)

    @classmethod
    def from_null_result(cls, url: str | None = None) -> "SnapshotError":
        """Create error for null snapshot result."""
        message = (
            "window.sentience.snapshot() returned null.\n\n"
            "Possible causes:\n"
            "  1. Extension is not properly initialized\n"
            "  2. Page DOM is in an invalid state\n"
            "  3. Extension encountered an internal error\n\n"
            "Try refreshing the page and taking a new snapshot."
        )
        if url:
            message = f"{message}\n  Page URL: {url}"
        return cls(message, url=url, raw_result=None)


class ActionError(SentienceBackendError):
    """
    Raised when a browser action (click, type, scroll) fails.
    """

    def __init__(
        self,
        action: str,
        message: str,
        coordinates: tuple[float, float] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        self.action = action
        self.coordinates = coordinates
        self.original_error = original_error
        super().__init__(f"{action} failed: {message}")
