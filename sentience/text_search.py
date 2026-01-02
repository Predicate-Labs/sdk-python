"""
Text search utilities - find text and get pixel coordinates
"""

from .browser import AsyncSentienceBrowser, SentienceBrowser
from .browser_evaluator import BrowserEvaluator
from .models import TextRectSearchResult


def find_text_rect(
    browser: SentienceBrowser,
    text: str,
    case_sensitive: bool = False,
    whole_word: bool = False,
    max_results: int = 10,
) -> TextRectSearchResult:
    """
    Find all occurrences of text on the page and get their exact pixel coordinates.

    This function searches for text in all visible text nodes on the page and returns
    the bounding rectangles for each match. Useful for:
    - Finding specific UI elements by their text content
    - Locating buttons, links, or labels without element IDs
    - Getting exact coordinates for click automation
    - Highlighting search results visually

    Args:
        browser: SentienceBrowser instance
        text: Text to search for (required)
        case_sensitive: If True, search is case-sensitive (default: False)
        whole_word: If True, only match whole words surrounded by whitespace (default: False)
        max_results: Maximum number of matches to return (default: 10, max: 100)

    Returns:
        TextRectSearchResult with:
            - status: "success" or "error"
            - query: The search text
            - case_sensitive: Whether search was case-sensitive
            - whole_word: Whether whole-word matching was used
            - matches: Number of matches found
            - results: List of TextMatch objects, each containing:
                - text: The matched text
                - rect: Absolute rectangle (with scroll offset)
                - viewport_rect: Viewport-relative rectangle
                - context: Surrounding text (before/after)
                - in_viewport: Whether visible in current viewport
            - viewport: Current viewport dimensions and scroll position
            - error: Error message if status is "error"

    Examples:
        # Find "Sign In" button
        result = find_text_rect(browser, "Sign In")
        if result.status == "success" and result.results:
            first_match = result.results[0]
            print(f"Found at: ({first_match.rect.x}, {first_match.rect.y})")
            print(f"Size: {first_match.rect.width}x{first_match.rect.height}")
            print(f"In viewport: {first_match.in_viewport}")

        # Case-sensitive search
        result = find_text_rect(browser, "LOGIN", case_sensitive=True)

        # Whole word only
        result = find_text_rect(browser, "log", whole_word=True)  # Won't match "login"

        # Find all matches and click the first visible one
        result = find_text_rect(browser, "Buy Now", max_results=5)
        if result.status == "success" and result.results:
            for match in result.results:
                if match.in_viewport:
                    # Use click_rect from actions module
                    from sentience import click_rect
                    click_result = click_rect(browser, {
                        "x": match.rect.x,
                        "y": match.rect.y,
                        "w": match.rect.width,
                        "h": match.rect.height
                    })
                    break
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")

    if not text or not text.strip():
        return TextRectSearchResult(
            status="error",
            error="Text parameter is required and cannot be empty",
        )

    # Limit max_results to prevent performance issues
    max_results = min(max_results, 100)

    # CRITICAL: Wait for extension injection to complete (CSP-resistant architecture)
    # The new architecture loads injected_api.js asynchronously, so window.sentience
    # may not be immediately available after page load
    BrowserEvaluator.wait_for_extension(browser.page, timeout_ms=5000)

    # Verify findTextRect method exists (for older extension versions that don't have it)
    if not BrowserEvaluator.verify_method_exists(browser.page, SentienceMethod.FIND_TEXT_RECT):
        raise RuntimeError(
            "window.sentience.findTextRect is not available. "
            "Please update the Sentience extension to the latest version."
        )

    # Call the extension's findTextRect method
    result_dict = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.findTextRect(options);
        }
        """,
        {
            "text": text,
            "caseSensitive": case_sensitive,
            "wholeWord": whole_word,
            "maxResults": max_results,
        },
    )

    # Parse and validate with Pydantic
    return TextRectSearchResult(**result_dict)


async def find_text_rect_async(
    browser: AsyncSentienceBrowser,
    text: str,
    case_sensitive: bool = False,
    whole_word: bool = False,
    max_results: int = 10,
) -> TextRectSearchResult:
    """
    Find all occurrences of text on the page and get their exact pixel coordinates (async).

    This function searches for text in all visible text nodes on the page and returns
    the bounding rectangles for each match. Useful for:
    - Finding specific UI elements by their text content
    - Locating buttons, links, or labels without element IDs
    - Getting exact coordinates for click automation
    - Highlighting search results visually

    Args:
        browser: AsyncSentienceBrowser instance
        text: Text to search for (required)
        case_sensitive: If True, search is case-sensitive (default: False)
        whole_word: If True, only match whole words surrounded by whitespace (default: False)
        max_results: Maximum number of matches to return (default: 10, max: 100)

    Returns:
        TextRectSearchResult with:
            - status: "success" or "error"
            - query: The search text
            - case_sensitive: Whether search was case-sensitive
            - whole_word: Whether whole-word matching was used
            - matches: Number of matches found
            - results: List of TextMatch objects, each containing:
                - text: The matched text
                - rect: Absolute rectangle (with scroll offset)
                - viewport_rect: Viewport-relative rectangle
                - context: Surrounding text (before/after)
                - in_viewport: Whether visible in current viewport
            - viewport: Current viewport dimensions and scroll position
            - error: Error message if status is "error"

    Examples:
        # Find "Sign In" button
        result = await find_text_rect_async(browser, "Sign In")
        if result.status == "success" and result.results:
            first_match = result.results[0]
            print(f"Found at: ({first_match.rect.x}, {first_match.rect.y})")
            print(f"Size: {first_match.rect.width}x{first_match.rect.height}")
            print(f"In viewport: {first_match.in_viewport}")

        # Case-sensitive search
        result = await find_text_rect_async(browser, "LOGIN", case_sensitive=True)

        # Whole word only
        result = await find_text_rect_async(browser, "log", whole_word=True)  # Won't match "login"

        # Find all matches and click the first visible one
        result = await find_text_rect_async(browser, "Buy Now", max_results=5)
        if result.status == "success" and result.results:
            for match in result.results:
                if match.in_viewport:
                    # Use click_rect_async from actions module
                    from sentience.actions import click_rect_async
                    click_result = await click_rect_async(browser, {
                        "x": match.rect.x,
                        "y": match.rect.y,
                        "w": match.rect.width,
                        "h": match.rect.height
                    })
                    break
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    if not text or not text.strip():
        return TextRectSearchResult(
            status="error",
            error="Text parameter is required and cannot be empty",
        )

    # Limit max_results to prevent performance issues
    max_results = min(max_results, 100)

    # CRITICAL: Wait for extension injection to complete (CSP-resistant architecture)
    # The new architecture loads injected_api.js asynchronously, so window.sentience
    # may not be immediately available after page load
    try:
        await browser.page.wait_for_function(
            "typeof window.sentience !== 'undefined'",
            timeout=5000,  # 5 second timeout
        )
    except Exception as e:
        # Gather diagnostics if wait fails
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

    # Verify findTextRect method exists (for older extension versions that don't have it)
    try:
        has_find_text_rect = await browser.page.evaluate(
            "typeof window.sentience.findTextRect !== 'undefined'"
        )
        if not has_find_text_rect:
            raise RuntimeError(
                "window.sentience.findTextRect is not available. "
                "Please update the Sentience extension to the latest version."
            )
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to verify findTextRect availability: {e}") from e

    # Call the extension's findTextRect method
    result_dict = await browser.page.evaluate(
        """
        (options) => {
            return window.sentience.findTextRect(options);
        }
        """,
        {
            "text": text,
            "caseSensitive": case_sensitive,
            "wholeWord": whole_word,
            "maxResults": max_results,
        },
    )

    # Parse and validate with Pydantic
    return TextRectSearchResult(**result_dict)
