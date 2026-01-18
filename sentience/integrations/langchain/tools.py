from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .context import SentienceLangChainContext
from .core import SentienceLangChainCore


def build_sentience_langchain_tools(ctx: SentienceLangChainContext) -> list[Any]:
    """
    Build LangChain tools backed by Sentience.

    LangChain is an optional dependency; imports are done lazily here so that
    `import sentience` works without LangChain installed.
    """

    try:
        from langchain_core.tools import StructuredTool
    except Exception:  # pragma: no cover
        from langchain.tools import StructuredTool  # type: ignore

    core = SentienceLangChainCore(ctx)

    # ---- Schemas ----
    class SnapshotStateArgs(BaseModel):
        limit: int = Field(50, ge=1, le=500, description="Max elements to return (default 50)")
        include_screenshot: bool = Field(
            False, description="Include screenshot in snapshot (default false)"
        )

    class ReadPageArgs(BaseModel):
        format: Literal["raw", "text", "markdown"] = Field("text", description="Output format")
        enhance_markdown: bool = Field(
            True, description="Enhance markdown conversion (default true)"
        )

    class ClickArgs(BaseModel):
        element_id: int = Field(..., description="Sentience element id from snapshot_state()")

    class TypeTextArgs(BaseModel):
        element_id: int = Field(..., description="Sentience element id from snapshot_state()")
        text: str = Field(..., description="Text to type")

    class PressKeyArgs(BaseModel):
        key: str = Field(..., description="Key to press (e.g., Enter, Escape, Tab)")

    class ScrollToArgs(BaseModel):
        element_id: int = Field(..., description="Sentience element id from snapshot_state()")
        behavior: Literal["smooth", "instant", "auto"] = Field(
            "smooth", description="Scroll behavior"
        )
        block: Literal["start", "center", "end", "nearest"] = Field(
            "center", description="Vertical alignment"
        )

    class NavigateArgs(BaseModel):
        url: str = Field(..., description="URL to navigate to")

    class ClickRectArgs(BaseModel):
        x: float = Field(..., description="Rect x (px)")
        y: float = Field(..., description="Rect y (px)")
        width: float = Field(..., description="Rect width (px)")
        height: float = Field(..., description="Rect height (px)")
        button: Literal["left", "right", "middle"] = Field("left", description="Mouse button")
        click_count: int = Field(1, ge=1, le=3, description="Click count")

    class FindTextRectArgs(BaseModel):
        text: str = Field(..., description="Text to search for")
        case_sensitive: bool = Field(False, description="Case sensitive search")
        whole_word: bool = Field(False, description="Whole-word match only")
        max_results: int = Field(10, ge=1, le=100, description="Max matches (capped at 100)")

    class VerifyUrlMatchesArgs(BaseModel):
        pattern: str = Field(..., description="Regex pattern to match against current URL")

    class VerifyTextPresentArgs(BaseModel):
        text: str = Field(..., description="Text to check for in read_page output")
        format: Literal["text", "markdown", "raw"] = Field("text", description="Read format")
        case_sensitive: bool = Field(False, description="Case sensitive check")

    class AssertEventuallyUrlMatchesArgs(BaseModel):
        pattern: str = Field(..., description="Regex pattern to match against current URL")
        timeout_s: float = Field(10.0, ge=0.1, description="Timeout seconds")
        poll_s: float = Field(0.25, ge=0.05, description="Polling interval seconds")

    # ---- Sync wrappers (explicitly unsupported) ----
    def _sync_unsupported(*args, **kwargs):
        raise RuntimeError(
            "Sentience LangChain tools are async-only. Use an async LangChain agent/runner."
        )

    # ---- Tools ----
    return [
        StructuredTool(
            name="sentience_snapshot_state",
            description="Observe: take a bounded Sentience snapshot and return a typed BrowserState (url + elements).",
            args_schema=SnapshotStateArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.snapshot_state(**kw),
        ),
        StructuredTool(
            name="sentience_read_page",
            description="Observe: read page content as text/markdown/raw HTML.",
            args_schema=ReadPageArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.read_page(**kw),
        ),
        StructuredTool(
            name="sentience_click",
            description="Act: click an element by element_id from snapshot_state.",
            args_schema=ClickArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.click(**kw),
        ),
        StructuredTool(
            name="sentience_type_text",
            description="Act: type text into an element by element_id from snapshot_state.",
            args_schema=TypeTextArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.type_text(**kw),
        ),
        StructuredTool(
            name="sentience_press_key",
            description="Act: press a keyboard key (Enter/Escape/Tab/etc.).",
            args_schema=PressKeyArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.press_key(**kw),
        ),
        StructuredTool(
            name="sentience_scroll_to",
            description="Act: scroll an element into view by element_id from snapshot_state.",
            args_schema=ScrollToArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.scroll_to(**kw),
        ),
        StructuredTool(
            name="sentience_navigate",
            description="Act: navigate to a URL using the underlying Playwright page.goto.",
            args_schema=NavigateArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.navigate(**kw),
        ),
        StructuredTool(
            name="sentience_click_rect",
            description="Act: click a rectangle by pixel coordinates (useful with find_text_rect).",
            args_schema=ClickRectArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.click_rect(**kw),
        ),
        StructuredTool(
            name="sentience_find_text_rect",
            description="Locate: find text occurrences on the page and return pixel coordinates.",
            args_schema=FindTextRectArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.find_text_rect(**kw),
        ),
        StructuredTool(
            name="sentience_verify_url_matches",
            description="Verify: check current URL matches a regex pattern (post-action guard).",
            args_schema=VerifyUrlMatchesArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.verify_url_matches(**kw),
        ),
        StructuredTool(
            name="sentience_verify_text_present",
            description="Verify: check that a text substring is present in read_page output.",
            args_schema=VerifyTextPresentArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.verify_text_present(**kw),
        ),
        StructuredTool(
            name="sentience_assert_eventually_url_matches",
            description="Verify: retry URL regex match until timeout (use for delayed navigation/redirects).",
            args_schema=AssertEventuallyUrlMatchesArgs,
            func=_sync_unsupported,
            coroutine=lambda **kw: core.assert_eventually_url_matches(**kw),
        ),
    ]
