"""
Read page content - enhanced markdown conversion
"""

from typing import Optional, Literal
from .browser import SentienceBrowser


def read(
    browser: SentienceBrowser,
    format: Literal["text", "markdown"] = "text",
    enhance_markdown: bool = True,
) -> dict:
    """
    Read page content as text or markdown
    
    Args:
        browser: SentienceBrowser instance
        format: Output format - "text" or "markdown"
        enhance_markdown: If True and format="markdown", use markdownify for better conversion
    
    Returns:
        dict with:
            - status: "success" or "error"
            - url: Current page URL
            - format: "text" or "markdown"
            - content: Page content as string
            - length: Content length in characters
            - error: Error message if status is "error"
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    
    # Get basic content from extension
    result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.read(options);
        }
        """,
        {"format": format},
    )
    
    # Enhance markdown if requested and format is markdown
    if format == "markdown" and enhance_markdown and result.get("status") == "success":
        try:
            # Get full HTML from page
            html_content = browser.page.evaluate("() => document.documentElement.outerHTML")
            
            # Use markdownify for better conversion
            from markdownify import markdownify as md
            enhanced_markdown = md(
                html_content,
                heading_style="ATX",  # Use # for headings
                bullets="-",  # Use - for lists
                strip=['script', 'style', 'nav', 'footer', 'header', 'noscript'],  # Strip unwanted tags
            )
            result["content"] = enhanced_markdown
            result["length"] = len(enhanced_markdown)
        except ImportError:
            # Fallback to extension's lightweight conversion if markdownify not installed
            # This shouldn't happen if dependencies are installed, but handle gracefully
            pass
        except Exception as e:
            # If enhancement fails, use extension's result
            # Don't overwrite result["error"] - keep extension's result
            pass
    
    return result

