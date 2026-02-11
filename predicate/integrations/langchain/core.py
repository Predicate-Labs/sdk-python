from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal

from predicate.actions import (
    click_async,
    click_rect_async,
    press_async,
    scroll_to_async,
    type_text_async,
)
from predicate.integrations.models import AssertionResult, BrowserState, ElementSummary
from predicate.models import ReadResult, SnapshotOptions, TextRectSearchResult
from predicate.read import read_async
from predicate.snapshot import snapshot_async
from predicate.text_search import find_text_rect_async
from predicate.trace_event_builder import TraceEventBuilder

from .context import SentienceLangChainContext


class SentienceLangChainCore:
    """
    Framework-agnostic (LangChain-friendly) async wrappers around Sentience SDK.

    - No LangChain imports
    - Optional Sentience tracing (local/cloud) if ctx.tracer is provided
    """

    def __init__(self, ctx: SentienceLangChainContext):
        self.ctx = ctx
        self._step_counter = 0

    def _safe_tracer_call(self, method_name: str, *args, **kwargs) -> None:
        tracer = self.ctx.tracer
        if not tracer:
            return
        try:
            getattr(tracer, method_name)(*args, **kwargs)
        except Exception:
            # Tracing must be non-fatal
            pass

    async def _trace(self, tool_name: str, exec_coro, exec_meta: dict[str, Any]):
        tracer = self.ctx.tracer
        browser = self.ctx.browser

        pre_url = getattr(getattr(browser, "page", None), "url", None)

        # Emit run_start once (best-effort)
        if tracer and getattr(tracer, "started_at", None) is None:
            self._safe_tracer_call(
                "emit_run_start",
                agent="LangChain+SentienceTools",
                llm_model=None,
                config={"integration": "langchain"},
            )

        step_id = None
        step_index = None
        start = time.time()
        if tracer:
            self._step_counter += 1
            step_index = self._step_counter
            step_id = f"tool-{step_index}:{tool_name}"
            self._safe_tracer_call(
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
                post_url = getattr(getattr(browser, "page", None), "url", pre_url)
                duration_ms = int((time.time() - start) * 1000)

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
                    post_snapshot_digest=None,
                    llm_data={},
                    exec_data=exec_data,
                    verify_data=verify_data,
                )
                self._safe_tracer_call("emit", "step_end", step_end_data, step_id=step_id)

            return result
        except Exception as e:
            if tracer and step_id:
                self._safe_tracer_call("emit_error", step_id=step_id, error=str(e), attempt=0)
            raise

    # ===== Observe =====
    async def snapshot_state(
        self, limit: int = 50, include_screenshot: bool = False
    ) -> BrowserState:
        async def _run():
            opts = SnapshotOptions(limit=limit, screenshot=include_screenshot)
            snap = await snapshot_async(self.ctx.browser, opts)
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

        return await self._trace(
            "snapshot_state",
            _run,
            {"limit": limit, "include_screenshot": include_screenshot},
        )

    async def read_page(
        self,
        format: Literal["raw", "text", "markdown"] = "text",
        enhance_markdown: bool = True,
    ) -> ReadResult:
        async def _run():
            return await read_async(
                self.ctx.browser, output_format=format, enhance_markdown=enhance_markdown
            )

        return await self._trace(
            "read_page",
            _run,
            {"format": format, "enhance_markdown": enhance_markdown},
        )

    # ===== Act =====
    async def click(self, element_id: int):
        return await self._trace(
            "click",
            lambda: click_async(self.ctx.browser, element_id),
            {"element_id": element_id},
        )

    async def type_text(self, element_id: int, text: str):
        # avoid tracing text (PII)
        return await self._trace(
            "type_text",
            lambda: type_text_async(self.ctx.browser, element_id, text),
            {"element_id": element_id},
        )

    async def press_key(self, key: str):
        return await self._trace(
            "press_key", lambda: press_async(self.ctx.browser, key), {"key": key}
        )

    async def scroll_to(
        self,
        element_id: int,
        behavior: Literal["smooth", "instant", "auto"] = "smooth",
        block: Literal["start", "center", "end", "nearest"] = "center",
    ):
        return await self._trace(
            "scroll_to",
            lambda: scroll_to_async(self.ctx.browser, element_id, behavior=behavior, block=block),
            {"element_id": element_id, "behavior": behavior, "block": block},
        )

    async def navigate(self, url: str) -> dict[str, Any]:
        async def _run():
            await self.ctx.browser.goto(url)
            post_url = getattr(getattr(self.ctx.browser, "page", None), "url", None)
            return {"success": True, "url": post_url or url}

        return await self._trace("navigate", _run, {"url": url})

    async def click_rect(
        self,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        button: Literal["left", "right", "middle"] = "left",
        click_count: int = 1,
    ):
        async def _run():
            return await click_rect_async(
                self.ctx.browser,
                {"x": x, "y": y, "w": width, "h": height},
                button=button,
                click_count=click_count,
            )

        return await self._trace(
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

    async def find_text_rect(
        self,
        text: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
        max_results: int = 10,
    ) -> TextRectSearchResult:
        async def _run():
            return await find_text_rect_async(
                self.ctx.browser,
                text,
                case_sensitive=case_sensitive,
                whole_word=whole_word,
                max_results=max_results,
            )

        return await self._trace(
            "find_text_rect",
            _run,
            {
                "query": text,
                "case_sensitive": case_sensitive,
                "whole_word": whole_word,
                "max_results": max_results,
            },
        )

    # ===== Verify / guard =====
    async def verify_url_matches(self, pattern: str, flags: int = 0) -> AssertionResult:
        async def _run():
            page = getattr(self.ctx.browser, "page", None)
            if not page:
                return AssertionResult(passed=False, reason="Browser not started (page is None)")
            url = page.url
            ok = re.search(pattern, url, flags) is not None
            return AssertionResult(
                passed=ok,
                reason="" if ok else f"URL did not match pattern. url={url!r} pattern={pattern!r}",
                details={"url": url, "pattern": pattern},
            )

        return await self._trace("verify_url_matches", _run, {"pattern": pattern})

    async def verify_text_present(
        self,
        text: str,
        *,
        format: Literal["text", "markdown", "raw"] = "text",
        case_sensitive: bool = False,
    ) -> AssertionResult:
        async def _run():
            result = await read_async(self.ctx.browser, output_format=format, enhance_markdown=True)
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

        return await self._trace("verify_text_present", _run, {"query": text, "format": format})

    async def assert_eventually_url_matches(
        self,
        pattern: str,
        *,
        timeout_s: float = 10.0,
        poll_s: float = 0.25,
        flags: int = 0,
    ) -> AssertionResult:
        deadline = time.monotonic() + timeout_s
        last: AssertionResult | None = None
        while time.monotonic() <= deadline:
            last = await self.verify_url_matches(pattern, flags)
            if last.passed:
                return last
            await asyncio.sleep(poll_s)
        return last or AssertionResult(passed=False, reason="No attempts executed", details={})
