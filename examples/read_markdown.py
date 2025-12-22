"""
Example: Reading page content and converting to markdown

This example shows how to use the read() function to get page content
and convert it to high-quality markdown using markdownify.
"""

from sentience import SentienceBrowser, read
from markdownify import markdownify


def main():
    # Initialize browser
    with SentienceBrowser(headless=True) as browser:
        # Navigate to a page
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        # Method 1: Get raw HTML (default) and convert with markdownify
        print("=== Method 1: Raw HTML + markdownify (Recommended) ===")
        result = read(browser)  # format="raw" is default
        html_content = result["content"]
        
        # Convert to markdown using markdownify (better quality)
        markdown = markdownify(
            html_content,
            heading_style="ATX",  # Use # for headings
            bullets="-",  # Use - for lists
            strip=['script', 'style', 'nav', 'footer', 'header'],  # Strip unwanted tags
        )
        print(f"Markdown length: {len(markdown)} characters")
        print(markdown[:500])  # Print first 500 chars
        print("\n")
        
        # Method 2: Get high-quality markdown directly (uses markdownify internally)
        print("=== Method 2: Direct markdown (High-quality via markdownify) ===")
        result = read(browser, format="markdown")
        high_quality_markdown = result["content"]
        print(f"Markdown length: {len(high_quality_markdown)} characters")
        print(high_quality_markdown[:500])  # Print first 500 chars
        print("\n")
        
        # Method 3: Get plain text
        print("=== Method 3: Plain text ===")
        result = read(browser, format="text")
        text_content = result["content"]
        print(f"Text length: {len(text_content)} characters")
        print(text_content[:500])  # Print first 500 chars


if __name__ == "__main__":
    main()

