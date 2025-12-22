"""
Read page content - supports raw HTML, text, and markdown formats
"""

from typing import Literal
from .browser import SentienceBrowser


def read(
    browser: SentienceBrowser,
    output_format: Literal["raw", "text", "markdown"] = "raw",
    enhance_markdown: bool = True,
) -> dict:
    """
    Read page content as raw HTML, text, or markdown
    
    Args:
        browser: SentienceBrowser instance
        output_format: Output format - "raw" (default, returns HTML for external processing),
                        "text" (plain text), or "markdown" (lightweight or enhanced markdown).
        enhance_markdown: If True and output_format is "markdown", uses markdownify for better conversion.
                          If False, uses the extension's lightweight markdown converter.
    
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
        result = read(browser, output_format="markdown")
        markdown = result["content"]
        
        # Get plain text
        result = read(browser, output_format="text")
        text = result["content"]
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call browser.start() first.")
    
    if output_format == "markdown" and enhance_markdown:
        # Get raw HTML from the extension first
        raw_html_result = browser.page.evaluate(
            """
            (options) => {
                return window.sentience.read(options);
            }
            """,
            {"format": "raw"},
        )
        
        if raw_html_result.get("status") == "success":
            html_content = raw_html_result["content"]
            try:
                # Use markdownify for enhanced markdown conversion
                from markdownify import markdownify, MarkdownifyError
                markdown_content = markdownify(html_content, heading_style="ATX", wrap=True)
                return {
                    "status": "success",
                    "url": raw_html_result["url"],
                    "format": "markdown",
                    "content": markdown_content,
                    "length": len(markdown_content),
                }
            except ImportError:
                print("Warning: 'markdownify' not installed. Install with 'pip install markdownify' for enhanced markdown. Falling back to extension's markdown.")
            except MarkdownifyError as e:
                print(f"Warning: markdownify failed ({e}), falling back to extension's markdown.")
            except Exception as e:
                print(f"Warning: An unexpected error occurred with markdownify ({e}), falling back to extension's markdown.")

    # If not enhanced markdown, or fallback, call extension with requested format
    result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.read(options);
        }
        """,
        {"format": output_format},
    )
    
    return result
