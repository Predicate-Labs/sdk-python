"""
Read page content - supports raw HTML, text, and markdown formats
"""

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from .browser import AsyncSentienceBrowser, SentienceBrowser
from .llm_provider import LLMProvider
from .models import ExtractResult, ReadResult


def read(
    browser: SentienceBrowser,
    output_format: Literal["raw", "text", "markdown"] = "raw",
    enhance_markdown: bool = True,
) -> ReadResult:
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
                from markdownify import MarkdownifyError, markdownify

                markdown_content = markdownify(html_content, heading_style="ATX", wrap=True)
                return ReadResult(
                    status="success",
                    url=raw_html_result["url"],
                    format="markdown",
                    content=markdown_content,
                    length=len(markdown_content),
                )
            except ImportError:
                print(
                    "Warning: 'markdownify' not installed. Install with 'pip install markdownify' for enhanced markdown. Falling back to extension's markdown."
                )
            except MarkdownifyError as e:
                print(f"Warning: markdownify failed ({e}), falling back to extension's markdown.")
            except Exception as e:
                print(
                    f"Warning: An unexpected error occurred with markdownify ({e}), falling back to extension's markdown."
                )

    # If not enhanced markdown, or fallback, call extension with requested format
    result = browser.page.evaluate(
        """
        (options) => {
            return window.sentience.read(options);
        }
        """,
        {"format": output_format},
    )

    # Convert dict result to ReadResult model
    return ReadResult(**result)


async def read_async(
    browser: AsyncSentienceBrowser,
    output_format: Literal["raw", "text", "markdown"] = "raw",
    enhance_markdown: bool = True,
) -> ReadResult:
    """
    Read page content as raw HTML, text, or markdown (async)

    Args:
        browser: AsyncSentienceBrowser instance
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
        result = await read_async(browser)
        html_content = result["content"]

        # Get high-quality markdown (uses markdownify internally)
        result = await read_async(browser, output_format="markdown")
        markdown = result["content"]

        # Get plain text
        result = await read_async(browser, output_format="text")
        text = result["content"]
    """
    if not browser.page:
        raise RuntimeError("Browser not started. Call await browser.start() first.")

    if output_format == "markdown" and enhance_markdown:
        # Get raw HTML from the extension first
        raw_html_result = await browser.page.evaluate(
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
                from markdownify import MarkdownifyError, markdownify

                markdown_content = markdownify(html_content, heading_style="ATX", wrap=True)
                return ReadResult(
                    status="success",
                    url=raw_html_result["url"],
                    format="markdown",
                    content=markdown_content,
                    length=len(markdown_content),
                )
            except ImportError:
                print(
                    "Warning: 'markdownify' not installed. Install with 'pip install markdownify' for enhanced markdown. Falling back to extension's markdown."
                )
            except MarkdownifyError as e:
                print(f"Warning: markdownify failed ({e}), falling back to extension's markdown.")
            except Exception as e:
                print(
                    f"Warning: An unexpected error occurred with markdownify ({e}), falling back to extension's markdown."
                )

    # If not enhanced markdown, or fallback, call extension with requested format
    result = await browser.page.evaluate(
        """
        (options) => {
            return window.sentience.read(options);
        }
        """,
        {"format": output_format},
    )

    # Convert dict result to ReadResult model
    return ReadResult(**result)


def _extract_json_payload(text: str) -> dict[str, Any]:
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))
    inline = re.search(r"(\{.*\})", text, re.DOTALL)
    if inline:
        return json.loads(inline.group(1))
    return json.loads(text)


def extract(
    browser: SentienceBrowser,
    llm: LLMProvider,
    query: str,
    schema: type[BaseModel] | None = None,
    max_chars: int = 12000,
) -> ExtractResult:
    """
    Extract structured data from the current page using read() markdown + LLM.
    """
    result = read(browser, output_format="markdown", enhance_markdown=True)
    if result.status != "success":
        return ExtractResult(ok=False, error=result.error)

    content = result.content[:max_chars]
    schema_desc = ""
    if schema is not None:
        schema_desc = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    system = "You extract structured data from markdown content. " "Return only JSON. No prose."
    user = f"QUERY:\n{query}\n\nSCHEMA:\n{schema_desc}\n\nCONTENT:\n{content}"
    response = llm.generate(system, user)
    raw = response.content.strip()

    if schema is None:
        return ExtractResult(ok=True, data={"text": raw}, raw=raw)

    try:
        payload = _extract_json_payload(raw)
        validated = schema.model_validate(payload)
        return ExtractResult(ok=True, data=validated, raw=raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        return ExtractResult(ok=False, error=str(exc), raw=raw)


async def extract_async(
    browser: AsyncSentienceBrowser,
    llm: LLMProvider,
    query: str,
    schema: type[BaseModel] | None = None,
    max_chars: int = 12000,
) -> ExtractResult:
    """
    Async version of extract().
    """
    result = await read_async(browser, output_format="markdown", enhance_markdown=True)
    if result.status != "success":
        return ExtractResult(ok=False, error=result.error)

    content = result.content[:max_chars]
    schema_desc = ""
    if schema is not None:
        schema_desc = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    system = "You extract structured data from markdown content. " "Return only JSON. No prose."
    user = f"QUERY:\n{query}\n\nSCHEMA:\n{schema_desc}\n\nCONTENT:\n{content}"
    response = await llm.generate_async(system, user)
    raw = response.content.strip()

    if schema is None:
        return ExtractResult(ok=True, data={"text": raw}, raw=raw)

    try:
        payload = _extract_json_payload(raw)
        validated = schema.model_validate(payload)
        return ExtractResult(ok=True, data=validated, raw=raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        return ExtractResult(ok=False, error=str(exc), raw=raw)
