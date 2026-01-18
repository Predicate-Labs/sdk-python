from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal

from sentience.actions import click_async, press_async, type_text_async
from sentience.integrations.models import AssertionResult, BrowserState, ElementSummary
from sentience.models import ReadResult, SnapshotOptions, TextRectSearchResult
from sentience.read import read_async
from sentience.snapshot import snapshot_async
from sentience.text_search import find_text_rect_async

from .deps import SentiencePydanticDeps


def register_sentience_tools(agent: Any) -> dict[str, Any]:
    """
    Register Sentience tools on a PydanticAI agent.

    This function is intentionally lightweight and avoids importing `pydantic_ai`
    at module import time. It expects `agent` to provide a `.tool` decorator
    compatible with PydanticAI's `Agent.tool`.

    Returns:
        Mapping of tool name -> underlying coroutine function (useful for tests).
    """

    @agent.tool
    async def snapshot_state(
        ctx: Any,
        limit: int = 50,
        include_screenshot: bool = False,
    ) -> BrowserState:
        """
        Take a bounded snapshot of the current page and return a small typed summary.
        """
        deps: SentiencePydanticDeps = ctx.deps
        opts = SnapshotOptions(limit=limit, screenshot=include_screenshot)
        snap = await snapshot_async(deps.browser, opts)
        elements = [
            ElementSummary(
                id=e.id,
                role=e.role,
                text=e.text,
                importance=e.importance,
                bbox=e.bbox,
            )
            for e in snap.elements
        ]
        return BrowserState(url=snap.url, elements=elements)

    @agent.tool
    async def read_page(
        ctx: Any,
        format: Literal["raw", "text", "markdown"] = "text",
        enhance_markdown: bool = True,
    ) -> ReadResult:
        """
        Read page content as raw HTML, text, or markdown.
        """
        deps: SentiencePydanticDeps = ctx.deps
        return await read_async(deps.browser, output_format=format, enhance_markdown=enhance_markdown)

    @agent.tool
    async def click(
        ctx: Any,
        element_id: int,
    ):
        """
        Click an element by Sentience element id (from snapshot).
        """
        deps: SentiencePydanticDeps = ctx.deps
        return await click_async(deps.browser, element_id)

    @agent.tool
    async def type_text(
        ctx: Any,
        element_id: int,
        text: str,
    ):
        """
        Type text into an element by Sentience element id (from snapshot).
        """
        deps: SentiencePydanticDeps = ctx.deps
        return await type_text_async(deps.browser, element_id, text)

    @agent.tool
    async def press_key(
        ctx: Any,
        key: str,
    ):
        """
        Press a keyboard key (Enter, Escape, Tab, etc.).
        """
        deps: SentiencePydanticDeps = ctx.deps
        return await press_async(deps.browser, key)

    @agent.tool
    async def find_text_rect(
        ctx: Any,
        text: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
        max_results: int = 10,
    ) -> TextRectSearchResult:
        """
        Find text occurrences and return pixel coordinates.
        """
        deps: SentiencePydanticDeps = ctx.deps
        return await find_text_rect_async(
            deps.browser,
            text,
            case_sensitive=case_sensitive,
            whole_word=whole_word,
            max_results=max_results,
        )

    @agent.tool
    async def verify_url_matches(
        ctx: Any,
        pattern: str,
        flags: int = 0,
    ) -> AssertionResult:
        """
        Verify the current page URL matches a regex pattern.
        """
        deps: SentiencePydanticDeps = ctx.deps
        if not deps.browser.page:
            return AssertionResult(passed=False, reason="Browser not started (page is None)")

        url = deps.browser.page.url
        ok = re.search(pattern, url, flags) is not None
        return AssertionResult(
            passed=ok,
            reason="" if ok else f"URL did not match pattern. url={url!r} pattern={pattern!r}",
            details={"url": url, "pattern": pattern},
        )

    @agent.tool
    async def verify_text_present(
        ctx: Any,
        text: str,
        *,
        format: Literal["text", "markdown", "raw"] = "text",
        case_sensitive: bool = False,
    ) -> AssertionResult:
        """
        Verify a text substring is present in `read_page()` output.
        """
        deps: SentiencePydanticDeps = ctx.deps
        result = await read_async(deps.browser, output_format=format, enhance_markdown=True)
        if result.status != "success":
            return AssertionResult(passed=False, reason=f"read failed: {result.error}", details={})

        haystack = result.content if case_sensitive else result.content.lower()
        needle = text if case_sensitive else text.lower()
        ok = needle in haystack
        return AssertionResult(
            passed=ok,
            reason="" if ok else f"Text not present: {text!r}",
            details={"format": format, "query": text, "length": result.length},
        )

    @agent.tool
    async def assert_eventually_url_matches(
        ctx: Any,
        pattern: str,
        *,
        timeout_s: float = 10.0,
        poll_s: float = 0.25,
        flags: int = 0,
    ) -> AssertionResult:
        """
        Retry until the page URL matches `pattern` or timeout is reached.
        """
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() <= deadline:
            last = await verify_url_matches(ctx, pattern, flags)
            if last.passed:
                return last
            await asyncio.sleep(poll_s)
        return last or AssertionResult(passed=False, reason="No attempts executed", details={})

    return {
        "snapshot_state": snapshot_state,
        "read_page": read_page,
        "click": click,
        "type_text": type_text,
        "press_key": press_key,
        "find_text_rect": find_text_rect,
        "verify_url_matches": verify_url_matches,
        "verify_text_present": verify_text_present,
        "assert_eventually_url_matches": assert_eventually_url_matches,
    }

