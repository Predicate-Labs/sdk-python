from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sentience.agent_runtime import AgentRuntime
from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues
from sentience.verification import AssertContext, AssertOutcome, is_checked, is_disabled, is_enabled, value_contains


class MockBackend:
    async def screenshot_png(self) -> bytes:
        return b""


class MockTracer:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        self.events.append({"type": event_type, "data": data, "step_id": step_id})


def make_element(
    element_id: int,
    *,
    role: str,
    text: str | None,
    disabled: bool | None = None,
    checked: bool | None = None,
    value: str | None = None,
    input_type: str | None = None,
) -> Element:
    return Element(
        id=element_id,
        role=role,
        text=text,
        importance=10,
        bbox=BBox(x=0, y=0, width=100, height=40),
        visual_cues=VisualCues(is_primary=False, is_clickable=True, background_color_name=None),
        in_viewport=True,
        is_occluded=False,
        disabled=disabled,
        checked=checked,
        value=value,
        input_type=input_type,
    )


def make_snapshot(elements: list[Element], url: str) -> Snapshot:
    return Snapshot(
        status="success",
        url=url,
        elements=elements,
        viewport=Viewport(width=1280, height=720),
    )


def test_v1_state_assertions_enabled_disabled_checked_value() -> None:
    runtime = AgentRuntime(backend=MockBackend(), tracer=MockTracer())
    runtime.begin_step(goal="Test")

    elements = [
        make_element(1, role="button", text="Submit", disabled=False),
        make_element(2, role="checkbox", text=None, checked=True),
        make_element(3, role="textbox", text=None, value="hello", input_type="text"),
        make_element(4, role="button", text="Disabled", disabled=True),
    ]
    runtime.last_snapshot = make_snapshot(elements, url="https://example.com")

    assert runtime.assert_(is_enabled("text~'Submit'"), label="enabled") is True
    assert runtime.assert_(is_disabled("text~'Disabled'"), label="disabled") is True
    assert runtime.assert_(is_checked("role=checkbox"), label="checked") is True
    assert runtime.assert_(value_contains("role=textbox", "hello"), label="value") is True


@pytest.mark.asyncio
async def test_eventually_retry_loop_succeeds() -> None:
    tracer = MockTracer()
    runtime = AgentRuntime(backend=MockBackend(), tracer=tracer)
    runtime.begin_step(goal="Test")

    snaps = [
        make_snapshot([], url="https://example.com"),
        make_snapshot([], url="https://example.com"),
        make_snapshot([], url="https://example.com/done"),
    ]

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    def pred(ctx: AssertContext) -> AssertOutcome:
        ok = (ctx.url or "").endswith("/done")
        return AssertOutcome(passed=ok, reason="" if ok else "not done", details={})

    ok = await runtime.check(pred, label="eventually_done").eventually(timeout_s=2.0, poll_s=0.0)
    assert ok is True


@pytest.mark.asyncio
async def test_min_confidence_snapshot_exhausted() -> None:
    tracer = MockTracer()
    runtime = AgentRuntime(backend=MockBackend(), tracer=tracer)
    runtime.begin_step(goal="Test")

    low_diag = MagicMock()
    low_diag.confidence = 0.1
    low_diag.model_dump = lambda: {"confidence": 0.1}

    snaps = [
        MagicMock(url="https://example.com", elements=[], diagnostics=low_diag),
        MagicMock(url="https://example.com", elements=[], diagnostics=low_diag),
    ]

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    def pred(_ctx: AssertContext) -> AssertOutcome:
        return AssertOutcome(passed=True, reason="would pass", details={})

    ok = await runtime.check(pred, label="min_confidence_gate").eventually(
        timeout_s=2.0,
        poll_s=0.0,
        min_confidence=0.7,
        max_snapshot_attempts=2,
    )
    assert ok is False
    details = runtime._assertions_this_step[0]["details"]
    assert details["reason_code"] == "snapshot_exhausted"


@pytest.mark.asyncio
async def test_golden_flow_same_snapshots_actions_no_captcha() -> None:
    tracer = MockTracer()
    runtime = AgentRuntime(backend=MockBackend(), tracer=tracer)
    runtime.begin_step(goal="Test")

    class FakeActionExecutor:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def execute(self, action: str) -> dict:
            self.actions.append(action)
            return {"success": True}

    executor = FakeActionExecutor()
    executor.execute("CLICK(1)")
    executor.execute('TYPE(2, "hello")')
    assert executor.actions == ["CLICK(1)", 'TYPE(2, "hello")']

    snaps = [
        make_snapshot([], url="https://example.com"),
        make_snapshot([], url="https://example.com/after"),
        make_snapshot([], url="https://example.com/done"),
    ]

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    def pred(ctx: AssertContext) -> AssertOutcome:
        ok = (ctx.url or "").endswith("/done")
        return AssertOutcome(passed=ok, reason="" if ok else "not done", details={})

    ok = await runtime.check(pred, label="golden_flow").eventually(timeout_s=2.0, poll_s=0.0)
    assert ok is True
