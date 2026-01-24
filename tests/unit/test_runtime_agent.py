from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sentience.agent_runtime import AgentRuntime
from sentience.llm_provider import LLMProvider, LLMResponse
from sentience.models import (
    BBox,
    Element,
    Snapshot,
    SnapshotDiagnostics,
    StepHookContext,
    Viewport,
    VisualCues,
)
from sentience.runtime_agent import RuntimeAgent, RuntimeStep, StepVerification
from sentience.verification import AssertContext, AssertOutcome


class MockTracer:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        self.events.append({"type": event_type, "data": data, "step_id": step_id})


class MockBackend:
    def __init__(self) -> None:
        self._url = "https://example.com/start"
        self.mouse_clicks: list[tuple[float, float]] = []
        self.typed: list[str] = []
        self.eval_calls: list[str] = []

    async def get_url(self) -> str:
        return self._url

    async def refresh_page_info(self):
        return None

    async def eval(self, expression: str):
        self.eval_calls.append(expression)
        # default: no canvas
        if "querySelectorAll('canvas')" in expression:
            return 0
        return None

    async def call(self, function_declaration: str, args=None):
        _ = function_declaration, args
        return None

    async def get_layout_metrics(self):
        return None

    async def screenshot_png(self) -> bytes:
        return b"png"

    async def screenshot_jpeg(self, quality: int | None = None) -> bytes:
        _ = quality
        return b"jpeg"

    async def mouse_move(self, x: float, y: float) -> None:
        _ = x, y
        return None

    async def mouse_click(self, x: float, y: float, button="left", click_count=1) -> None:
        _ = button, click_count
        self.mouse_clicks.append((float(x), float(y)))

    async def wheel(self, delta_y: float, x=None, y=None) -> None:
        _ = delta_y, x, y
        return None

    async def type_text(self, text: str) -> None:
        self.typed.append(text)

    async def wait_ready_state(self, state="interactive", timeout_ms=15000) -> None:
        _ = state, timeout_ms
        return None


class ProviderStub(LLMProvider):
    def __init__(self, *, model: str = "stub", responses: list[str] | None = None):
        super().__init__(model)
        self._responses = responses or []
        self.calls: list[dict] = []

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        self.calls.append({"system": system_prompt, "user": user_prompt, "kwargs": kwargs})
        content = self._responses.pop(0) if self._responses else "FINISH()"
        return LLMResponse(content=content, model_name=self.model_name)

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return self._model_name


class VisionProviderStub(ProviderStub):
    def supports_vision(self) -> bool:
        return True

    def generate_with_image(
        self, system_prompt: str, user_prompt: str, image_base64: str, **kwargs
    ):
        self.calls.append(
            {
                "system": system_prompt,
                "user": user_prompt,
                "image_base64": image_base64,
                "kwargs": kwargs,
            }
        )
        content = self._responses.pop(0) if self._responses else "FINISH()"
        return LLMResponse(content=content, model_name=self.model_name)


def make_snapshot(
    *, url: str, elements: list[Element], confidence: float | None = None
) -> Snapshot:
    diagnostics = SnapshotDiagnostics(confidence=confidence) if confidence is not None else None
    return Snapshot(
        status="success",
        url=url,
        elements=elements,
        viewport=Viewport(width=1280, height=720),
        diagnostics=diagnostics,
    )


def make_clickable_element(element_id: int) -> Element:
    return Element(
        id=element_id,
        role="button",
        text="OK",
        importance=100,
        bbox=BBox(x=10, y=20, width=100, height=40),
        visual_cues=VisualCues(is_primary=True, is_clickable=True, background_color_name=None),
        in_viewport=True,
        is_occluded=False,
    )


@pytest.mark.asyncio
async def test_runtime_agent_structured_executor_success_no_vision_used() -> None:
    backend = MockBackend()
    tracer = MockTracer()
    runtime = AgentRuntime(backend=backend, tracer=tracer)

    # snapshot (ramp) -> S0, then verification eventually -> S1
    s0 = make_snapshot(url="https://example.com/start", elements=[make_clickable_element(1)])
    s1 = make_snapshot(url="https://example.com/done", elements=[make_clickable_element(1)])

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    snaps = [s0, s1]
    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    executor = ProviderStub(responses=["CLICK(1)"])
    agent = RuntimeAgent(runtime=runtime, executor=executor, vision_executor=None)

    def pred(ctx: AssertContext) -> AssertOutcome:
        ok = (ctx.url or "").endswith("/done")
        return AssertOutcome(passed=ok, reason="" if ok else "not done", details={})

    step = RuntimeStep(
        goal="Click OK",
        verifications=[
            StepVerification(
                predicate=pred,
                label="url_done",
                required=True,
                eventually=True,
                timeout_s=0.1,
                poll_s=0.0,
                max_snapshot_attempts=1,
            )
        ],
        max_snapshot_attempts=1,
    )

    ok = await agent.run_step(task_goal="test", step=step)
    assert ok is True
    assert len(executor.calls) == 1
    assert backend.mouse_clicks  # click happened


@pytest.mark.asyncio
async def test_runtime_agent_vision_executor_fallback_after_verification_fail() -> None:
    backend = MockBackend()
    tracer = MockTracer()
    runtime = AgentRuntime(backend=backend, tracer=tracer)

    s0 = make_snapshot(url="https://example.com/start", elements=[make_clickable_element(1)])
    s1 = make_snapshot(url="https://example.com/still", elements=[make_clickable_element(1)])
    s2 = make_snapshot(url="https://example.com/done", elements=[make_clickable_element(1)])

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    # ramp -> s0, first verification -> s1 (fail), second verification -> s2 (pass)
    snaps = [s0, s1, s2]
    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    executor = ProviderStub(responses=["CLICK(1)"])
    vision = VisionProviderStub(responses=["CLICK(1)"])
    agent = RuntimeAgent(runtime=runtime, executor=executor, vision_executor=vision)

    def pred(ctx: AssertContext) -> AssertOutcome:
        ok = (ctx.url or "").endswith("/done")
        return AssertOutcome(passed=ok, reason="" if ok else "not done", details={})

    step = RuntimeStep(
        goal="Try click; fallback if needed",
        verifications=[
            StepVerification(
                predicate=pred,
                label="url_done",
                required=True,
                eventually=True,
                timeout_s=0.0,
                poll_s=0.0,
                max_snapshot_attempts=1,
            )
        ],
        max_snapshot_attempts=1,
        vision_executor_enabled=True,
        max_vision_executor_attempts=1,
    )

    ok = await agent.run_step(task_goal="test", step=step)
    assert ok is True
    assert len(executor.calls) == 1
    assert len(vision.calls) == 1


@pytest.mark.asyncio
async def test_runtime_agent_hooks_called() -> None:
    backend = MockBackend()
    tracer = MockTracer()
    runtime = AgentRuntime(backend=backend, tracer=tracer)
    executor = ProviderStub(responses=["CLICK(1)"])

    agent = RuntimeAgent(runtime=runtime, executor=executor)
    step = RuntimeStep(goal="click first", verifications=[], max_snapshot_attempts=1)

    started: list[StepHookContext] = []
    ended: list[StepHookContext] = []

    async def on_start(ctx: StepHookContext):
        started.append(ctx)

    async def on_end(ctx: StepHookContext):
        ended.append(ctx)

    snapshot = make_snapshot(url="https://example.com/start", elements=[make_clickable_element(1)])

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snapshot
        return snapshot

    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    await agent.run_step(task_goal="task", step=step, on_step_start=on_start, on_step_end=on_end)

    assert len(started) == 1
    assert len(ended) == 1
    assert started[0].goal == "click first"
    assert ended[0].success is True
    assert ended[0].outcome == "ok"
    assert ended[0].error is None


@pytest.mark.asyncio
async def test_snapshot_limit_ramp_increases_limit_on_low_confidence() -> None:
    backend = MockBackend()
    tracer = MockTracer()
    runtime = AgentRuntime(backend=backend, tracer=tracer)

    s_low = make_snapshot(
        url="https://example.com/start", elements=[make_clickable_element(1)], confidence=0.1
    )
    s_hi = make_snapshot(
        url="https://example.com/start", elements=[make_clickable_element(1)], confidence=0.9
    )
    s_done = make_snapshot(url="https://example.com/done", elements=[make_clickable_element(1)])

    seen_limits: list[int] = []

    async def fake_snapshot(**kwargs):
        if kwargs.get("limit") is not None:
            seen_limits.append(int(kwargs["limit"]))
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    # ramp tries low then high; verification uses done
    snaps = [s_low, s_hi, s_done]
    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    executor = ProviderStub(responses=["CLICK(1)"])
    agent = RuntimeAgent(runtime=runtime, executor=executor)

    def pred(ctx: AssertContext) -> AssertOutcome:
        ok = (ctx.url or "").endswith("/done")
        return AssertOutcome(passed=ok, reason="" if ok else "not done", details={})

    step = RuntimeStep(
        goal="ramp snapshot",
        min_confidence=0.7,
        snapshot_limit_base=60,
        snapshot_limit_step=40,
        snapshot_limit_max=220,
        max_snapshot_attempts=2,
        verifications=[
            StepVerification(
                predicate=pred,
                label="url_done",
                required=True,
                eventually=True,
                timeout_s=0.1,
                poll_s=0.0,
                max_snapshot_attempts=1,
            )
        ],
    )

    ok = await agent.run_step(task_goal="test", step=step)
    assert ok is True
    assert seen_limits[:2] == [60, 100]


@pytest.mark.asyncio
async def test_short_circuit_to_vision_on_canvas_and_low_actionables() -> None:
    backend = MockBackend()

    async def eval_canvas(expression: str):
        backend.eval_calls.append(expression)
        if "querySelectorAll('canvas')" in expression:
            return 1
        return None

    backend.eval = eval_canvas  # type: ignore[method-assign]

    tracer = MockTracer()
    runtime = AgentRuntime(backend=backend, tracer=tracer)

    s0 = make_snapshot(url="https://example.com/start", elements=[])  # no actionables
    s1 = make_snapshot(url="https://example.com/done", elements=[])

    async def fake_snapshot(**_kwargs):
        runtime.last_snapshot = snaps.pop(0)
        return runtime.last_snapshot

    snaps = [s0, s1]
    runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

    executor = ProviderStub(responses=["CLICK(999)"])  # should NOT be called
    vision = VisionProviderStub(responses=["CLICK_XY(100, 200)"])
    agent = RuntimeAgent(
        runtime=runtime, executor=executor, vision_executor=vision, short_circuit_canvas=True
    )

    def pred(ctx: AssertContext) -> AssertOutcome:
        ok = (ctx.url or "").endswith("/done")
        return AssertOutcome(passed=ok, reason="" if ok else "not done", details={})

    step = RuntimeStep(
        goal="canvas step",
        min_actionables=1,
        max_snapshot_attempts=1,
        verifications=[
            StepVerification(
                predicate=pred,
                label="url_done",
                required=True,
                eventually=True,
                timeout_s=0.1,
                poll_s=0.0,
                max_snapshot_attempts=1,
            )
        ],
        vision_executor_enabled=True,
        max_vision_executor_attempts=1,
    )

    ok = await agent.run_step(task_goal="test", step=step)
    assert ok is True
    assert len(executor.calls) == 0
    assert len(vision.calls) == 1
    assert backend.mouse_clicks == [(100.0, 200.0)]
