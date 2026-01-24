from __future__ import annotations

from pydantic import BaseModel, Field

from ..agent_runtime import AgentRuntime
from ..backends import actions as backend_actions
from ..models import ActionResult, BBox, EvaluateJsRequest, Snapshot
from .context import ToolContext
from .registry import ToolRegistry


class SnapshotToolInput(BaseModel):
    limit: int = Field(50, ge=1, le=500, description="Max elements to return.")


class ClickToolInput(BaseModel):
    element_id: int = Field(..., ge=1, description="Sentience element id from snapshot.")


class TypeToolInput(BaseModel):
    element_id: int = Field(..., ge=1, description="Sentience element id from snapshot.")
    text: str = Field(..., min_length=1, description="Text to type into the element.")
    clear_first: bool = Field(False, description="Clear existing content before typing.")


class ScrollToolInput(BaseModel):
    delta_y: float = Field(..., description="Scroll amount (positive = down, negative = up).")
    x: float | None = Field(None, description="Optional scroll x coordinate.")
    y: float | None = Field(None, description="Optional scroll y coordinate.")


class ScrollToElementToolInput(BaseModel):
    element_id: int = Field(..., ge=1, description="Sentience element id from snapshot.")
    behavior: str = Field("instant", description="Scroll behavior.")
    block: str = Field("center", description="Vertical alignment.")


class ClickRectToolInput(BaseModel):
    x: float = Field(..., description="Rect x coordinate.")
    y: float = Field(..., description="Rect y coordinate.")
    width: float = Field(..., ge=0, description="Rect width.")
    height: float = Field(..., ge=0, description="Rect height.")


class PressToolInput(BaseModel):
    key: str = Field(..., min_length=1, description="Key to press (e.g., Enter).")


class EvaluateJsToolInput(BaseModel):
    code: str = Field(..., min_length=1, max_length=8000, description="JavaScript to execute.")
    max_output_chars: int = Field(4000, ge=1, le=20000, description="Output cap.")
    truncate: bool = Field(True, description="Truncate output when too long.")


def register_default_tools(
    registry: ToolRegistry, runtime: ToolContext | AgentRuntime | None = None
) -> ToolRegistry:
    """Register default browser tools on a registry."""

    def _get_runtime(ctx: ToolContext | None):
        if ctx is not None:
            return ctx.runtime
        if runtime is not None:
            if isinstance(runtime, ToolContext):
                return runtime.runtime
            return runtime
        raise RuntimeError("ToolContext with runtime is required")

    @registry.tool(
        name="snapshot_state",
        input_model=SnapshotToolInput,
        output_model=Snapshot,
        description="Capture a snapshot of the current page state.",
    )
    async def snapshot_state(ctx, params: SnapshotToolInput) -> Snapshot:
        runtime_ref = _get_runtime(ctx)
        snap = await runtime_ref.snapshot(limit=params.limit, goal="tool_snapshot_state")
        if snap is None:
            raise RuntimeError("snapshot() returned None")
        return snap

    @registry.tool(
        name="click",
        input_model=ClickToolInput,
        output_model=ActionResult,
        description="Click an element by id from the latest snapshot.",
    )
    async def click_tool(ctx, params: ClickToolInput) -> ActionResult:
        runtime_ref = _get_runtime(ctx)
        snap = runtime_ref.last_snapshot or await runtime_ref.snapshot(goal="tool_click")
        if snap is None:
            raise RuntimeError("snapshot() returned None")
        el = next((e for e in snap.elements if e.id == params.element_id), None)
        if el is None:
            raise ValueError(f"element_id not found: {params.element_id}")
        return await backend_actions.click(runtime_ref.backend, el.bbox)

    @registry.tool(
        name="type",
        input_model=TypeToolInput,
        output_model=ActionResult,
        description="Type text into an element by id from the latest snapshot.",
    )
    async def type_tool(ctx, params: TypeToolInput) -> ActionResult:
        runtime_ref = _get_runtime(ctx)
        snap = runtime_ref.last_snapshot or await runtime_ref.snapshot(goal="tool_type")
        if snap is None:
            raise RuntimeError("snapshot() returned None")
        el = next((e for e in snap.elements if e.id == params.element_id), None)
        if el is None:
            raise ValueError(f"element_id not found: {params.element_id}")
        return await backend_actions.type_text(
            runtime_ref.backend, params.text, target=el.bbox, clear_first=params.clear_first
        )

    @registry.tool(
        name="scroll",
        input_model=ScrollToolInput,
        output_model=ActionResult,
        description="Scroll the page by a delta amount.",
    )
    async def scroll_tool(ctx, params: ScrollToolInput) -> ActionResult:
        runtime_ref = _get_runtime(ctx)
        target = None
        if params.x is not None and params.y is not None:
            target = (params.x, params.y)
        return await backend_actions.scroll(runtime_ref.backend, params.delta_y, target=target)

    @registry.tool(
        name="scroll_to_element",
        input_model=ScrollToElementToolInput,
        output_model=ActionResult,
        description="Scroll a specific element into view by element id.",
    )
    async def scroll_to_element_tool(ctx, params: ScrollToElementToolInput) -> ActionResult:
        if ctx is not None:
            ctx.require("evaluate_js")
        runtime_ref = _get_runtime(ctx)
        return await backend_actions.scroll_to_element(
            runtime_ref.backend,
            params.element_id,
            behavior=params.behavior,
            block=params.block,
        )

    @registry.tool(
        name="click_rect",
        input_model=ClickRectToolInput,
        output_model=ActionResult,
        description="Click the center of a rectangle.",
    )
    async def click_rect_tool(ctx, params: ClickRectToolInput) -> ActionResult:
        runtime_ref = _get_runtime(ctx)
        bbox = BBox(
            x=params.x,
            y=params.y,
            width=params.width,
            height=params.height,
        )
        return await backend_actions.click(runtime_ref.backend, bbox)

    @registry.tool(
        name="press",
        input_model=PressToolInput,
        output_model=ActionResult,
        description="Press a keyboard key on the active element.",
    )
    async def press_tool(ctx, params: PressToolInput) -> ActionResult:
        if ctx is not None:
            ctx.require("keyboard")
        runtime_ref = _get_runtime(ctx)
        page = getattr(runtime_ref.backend, "_page", None) or getattr(
            runtime_ref.backend, "page", None
        )
        if page is not None and getattr(page, "keyboard", None) is not None:
            await page.keyboard.press(params.key)
            return ActionResult(success=True, duration_ms=0, outcome="dom_updated")
        try:
            await runtime_ref.backend.eval(
                f"""
                (() => {{
                    const el = document.activeElement;
                    if (!el) return false;
                    const key = {params.key!r};
                    el.dispatchEvent(new KeyboardEvent('keydown', {{ key }}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {{ key }}));
                    return true;
                }})()
                """
            )
            return ActionResult(success=True, duration_ms=0, outcome="dom_updated")
        except Exception as exc:
            return ActionResult(
                success=False,
                duration_ms=0,
                outcome="error",
                error={"code": "press_failed", "reason": str(exc)},
            )

    @registry.tool(
        name="evaluate_js",
        input_model=EvaluateJsToolInput,
        output_model=ActionResult,
        description="Evaluate JavaScript in the page context (returns text output).",
    )
    async def evaluate_js_tool(ctx, params: EvaluateJsToolInput) -> ActionResult:
        if ctx is not None:
            ctx.require("evaluate_js")
        runtime_ref = _get_runtime(ctx)
        result = await runtime_ref.evaluate_js(
            EvaluateJsRequest(
                code=params.code,
                max_output_chars=params.max_output_chars,
                truncate=params.truncate,
            )
        )
        if not result.ok:
            return ActionResult(
                success=False,
                duration_ms=0,
                outcome="error",
                error={"code": "evaluate_js_failed", "reason": result.error or "error"},
            )
        return ActionResult(
            success=True,
            duration_ms=0,
            outcome="dom_updated",
        )

    return registry
