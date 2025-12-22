"""
Read page content - supports raw HTML, text, and markdown formats
"""

from typing import Literal
from .browser import SentienceBrowser


def read(
    browser: SentienceBrowser,
    format: Literal["raw", "text", "markdown"] = "raw",  # noqa: A002
) -> dict:
    """
    Read page content as raw HTML, text, or markdown
    
    Args:
        browser: SentienceBrowser instance
        format: Output format - "raw" (default, returns HTML for Turndown/markdownify),
                "text" (plain text), or "markdown" (high-quality markdown via markdownify)
    
    Returns:
        dict with:
            - status: "success" or "error"
            - url: Current page URL
            - format: "raw", "text", or "markdown"
            - content: Page content as string
            - length: Content length in characters
            - error: Error message if status is "error"
    
    Examples:
        # Get raw HTML (default) - can be used with markdownify for better conversion
        result = read(browser)
        html_content = result["content"]
        
        # Get high-quality markdown (uses markdownify internally)
        result = read(browser, format="markdown")
        markdown = result["content"]
        
        # Get plain text
        result = read(browser, format="text")
        text = result["content"]
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    
    # For markdown format, get raw HTML first, then convert with markdownify
    if format == "markdown":
        # Get raw HTML from extension
        raw_result = browser.page.evaluate(
            """
            (options) => {
                return window.sentience.read(options);
            }
            """,
            {"format": "raw"},
        )
        
        if raw_result.get("status") != "success":
            return raw_result
        
        # Convert to markdown using markdownify
        try:
            from markdownify import markdownify as md
            html_content = raw_result["content"]
            markdown_content = md(
                html_content,
                heading_style="ATX",  # Use # for headings
                bullets="-",  # Use - for lists
                strip=['script', 'style', 'nav', 'footer', 'header', 'noscript'],  # Strip unwanted tags
            )
            
            # Return result with markdown content
            return {
                "status": "success",
                "url": raw_result["url"],
                "format": "markdown",
                "content": markdown_content,
                "length": len(markdown_content),
            }
        except ImportError:
            # Fallback to extension's lightweight markdown if markdownify not installed
            result = browser.page.evaluate(
                """
                (options) => {
                    return window.sentience.read(options);
                }
                """,
                {"format": "markdown"},
            )
            return result
        except (ValueError, TypeError, AttributeError) as e:
            # If conversion fails, return error
            return {
                "status": "error",
                "url": raw_result.get("url", ""),
                "format": "markdown",
                "content": "",
                "length": 0,
                "error": f"Markdown conversion failed: {e}",
            }
    else:
        # For "raw" or "text", call extension directly
        result = browser.page.evaluate(
            """
            (options) => {
                return window.sentience.read(options);
            }
            """,
            {"format": format},
        )
        return result
