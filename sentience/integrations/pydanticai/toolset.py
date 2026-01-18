from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal

from sentience.actions import (
    click_async,
    click_rect_async,
    press_async,
    scroll_to_async,
    type_text_async,
)
from sentience.integrations.models import AssertionResult, BrowserState, ElementSummary
from sentience.models import ReadResult, SnapshotOptions, TextRectSearchResult
from sentience.read import read_async
from sentience.snapshot import snapshot_async
from sentience.text_search import find_text_rect_async
from sentience.trace_event_builder import TraceEventBuilder

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

    # Per-agent counter for tool call steps (for tracing)
    step_counter = {"n": 0}

    def _safe_tracer_call(tracer: Any, method_name: str, *args, **kwargs) -> None:
        try:
            getattr(tracer, method_name)(*args, **kwargs)
        except Exception:
            # Tracing must be non-fatal for tool execution
            pass

    async def _trace_tool_call(ctx: Any, tool_name: str, exec_coro, exec_meta: dict[str, Any]):
        """
        Wrap a tool execution with Sentience tracing if a tracer is present in deps.
        """
        deps: SentiencePydanticDeps = ctx.deps
        tracer = deps.tracer

        pre_url = None
        if getattr(deps.browser, "page", None) is not None:
            pre_url = getattr(deps.browser.page, "url", None)

        # Initialize run_start once (best-effort)
        if tracer and getattr(tracer, "started_at", None) is None:
            _safe_tracer_call(
                tracer,
                "emit_run_start",
                agent="PydanticAI+SentienceToolset",
                llm_model=None,
                config={"integration": "pydanticai"},
            )

        step_id = None
        step_index = None
        start = time.time()
        if tracer:
            step_counter["n"] += 1
            step_index = step_counter["n"]
            step_id = f"tool-{step_index}:{tool_name}"
            _safe_tracer_call(
                tracer,
                "emit_step_start",
                step_id=step_id,
                step_index=step_index,
                goal=f"tool:{tool_name}",
                attempt=0,
                pre_url=pre_url,
            )

        try:
            result = await exec_coro()

            if tracer and step_id and step_index:
                post_url = pre_url
                if getattr(deps.browser, "page", None) is not None:
                    post_url = getattr(deps.browser.page, "url", pre_url)

                duration_ms = int((time.time() - start) * 1000)

                # Best-effort success inference
                success: bool | None = None
                if hasattr(result, "success"):
                    success = bool(getattr(result, "success"))
                elif hasattr(result, "status"):
                    success = getattr(result, "status") == "success"
                elif isinstance(result, dict):
                    if "success" in result:
                        try:
                            success = bool(result.get("success"))
                        except Exception:
                            success = None
                    elif "status" in result:
                        success = result.get("status") == "success"

                exec_data = {"tool": tool_name, "duration_ms": duration_ms, **exec_meta}
                if success is not None:
                    exec_data["success"] = success

                verify_data = {
                    "passed": bool(success) if success is not None else True,
                    "signals": {},
                }

                step_end_data = TraceEventBuilder.build_step_end_event(
                    step_id=step_id,
                    step_index=step_index,
                    goal=f"tool:{tool_name}",
                    attempt=0,
                    pre_url=pre_url or "",
                    post_url=post_url or "",
                    snapshot_digest=None,
                    llm_data={},
                    exec_data=exec_data,
                    verify_data=verify_data,
                )
                _safe_tracer_call(tracer, "emit", "step_end", step_end_data, step_id=step_id)

            return result

        except Exception as e:
            if tracer and step_id:
                _safe_tracer_call(tracer, "emit_error", step_id=step_id, error=str(e), attempt=0)
            raise

    @agent.tool
    async def snapshot_state(
        ctx: Any,
        limit: int = 50,
        include_screenshot: bool = False,
    ) -> BrowserState:
        """
        Take a bounded snapshot of the current page and return a small typed summary.
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            opts = SnapshotOptions(limit=limit, screenshot=include_screenshot)
            snap = await snapshot_async(deps.browser, opts)
            if getattr(snap, "status", "success") != "success":
                raise RuntimeError(getattr(snap, "error", None) or "snapshot failed")
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

        return await _trace_tool_call(
            ctx,
            "snapshot_state",
            _run,
            {"limit": limit, "include_screenshot": include_screenshot},
        )

    @agent.tool
    async def read_page(
        ctx: Any,
        format: Literal["raw", "text", "markdown"] = "text",
        enhance_markdown: bool = True,
    ) -> ReadResult:
        """
        Read page content as raw HTML, text, or markdown.
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await read_async(
                deps.browser,
                output_format=format,
                enhance_markdown=enhance_markdown,
            )

        return await _trace_tool_call(
            ctx,
            "read_page",
            _run,
            {"format": format, "enhance_markdown": enhance_markdown},
        )

    @agent.tool
    async def click(
        ctx: Any,
        element_id: int,
    ):
        """
        Click an element by Sentience element id (from snapshot).
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await click_async(deps.browser, element_id)

        return await _trace_tool_call(ctx, "click", _run, {"element_id": element_id})

    @agent.tool
    async def type_text(
        ctx: Any,
        element_id: int,
        text: str,
    ):
        """
        Type text into an element by Sentience element id (from snapshot).
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await type_text_async(deps.browser, element_id, text)

        # NOTE: we intentionally don't trace full `text` to avoid accidental PII leakage
        return await _trace_tool_call(ctx, "type_text", _run, {"element_id": element_id})

    @agent.tool
    async def press_key(
        ctx: Any,
        key: str,
    ):
        """
        Press a keyboard key (Enter, Escape, Tab, etc.).
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await press_async(deps.browser, key)

        return await _trace_tool_call(ctx, "press_key", _run, {"key": key})

    @agent.tool
    async def scroll_to(
        ctx: Any,
        element_id: int,
        behavior: Literal["smooth", "instant", "auto"] = "smooth",
        block: Literal["start", "center", "end", "nearest"] = "center",
    ):
        """
        Scroll an element into view by Sentience element id (from snapshot).
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await scroll_to_async(deps.browser, element_id, behavior=behavior, block=block)

        return await _trace_tool_call(
            ctx,
            "scroll_to",
            _run,
            {"element_id": element_id, "behavior": behavior, "block": block},
        )

    @agent.tool
    async def navigate(
        ctx: Any,
        url: str,
    ) -> dict[str, Any]:
        """
        Navigate to a URL using Playwright page.goto via AsyncSentienceBrowser.
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            await deps.browser.goto(url)
            post_url = None
            if getattr(deps.browser, "page", None) is not None:
                post_url = getattr(deps.browser.page, "url", None)
            return {"success": True, "url": post_url or url}

        return await _trace_tool_call(ctx, "navigate", _run, {"url": url})

    @agent.tool
    async def click_rect(
        ctx: Any,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        button: Literal["left", "right", "middle"] = "left",
        click_count: int = 1,
    ):
        """
        Click by pixel coordinates (rectangle), useful with `find_text_rect`.
        """

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await click_rect_async(
                deps.browser,
                {"x": x, "y": y, "w": width, "h": height},
                button=button,
                click_count=click_count,
            )

        return await _trace_tool_call(
            ctx,
            "click_rect",
            _run,
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "button": button,
                "click_count": click_count,
            },
        )

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

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            return await find_text_rect_async(
                deps.browser,
                text,
                case_sensitive=case_sensitive,
                whole_word=whole_word,
                max_results=max_results,
            )

        return await _trace_tool_call(
            ctx,
            "find_text_rect",
            _run,
            {
                "query": text,
                "case_sensitive": case_sensitive,
                "whole_word": whole_word,
                "max_results": max_results,
            },
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

        async def _run():
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

        return await _trace_tool_call(
            ctx,
            "verify_url_matches",
            _run,
            {"pattern": pattern},
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

        async def _run():
            deps: SentiencePydanticDeps = ctx.deps
            result = await read_async(deps.browser, output_format=format, enhance_markdown=True)
            if result.status != "success":
                return AssertionResult(
                    passed=False, reason=f"read failed: {result.error}", details={}
                )

            haystack = result.content if case_sensitive else result.content.lower()
            needle = text if case_sensitive else text.lower()
            ok = needle in haystack
            return AssertionResult(
                passed=ok,
                reason="" if ok else f"Text not present: {text!r}",
                details={"format": format, "query": text, "length": result.length},
            )

        return await _trace_tool_call(
            ctx,
            "verify_text_present",
            _run,
            {"query": text, "format": format},
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
        "scroll_to": scroll_to,
        "navigate": navigate,
        "click_rect": click_rect,
        "find_text_rect": find_text_rect,
        "verify_url_matches": verify_url_matches,
        "verify_text_present": verify_text_present,
        "assert_eventually_url_matches": assert_eventually_url_matches,
    }
