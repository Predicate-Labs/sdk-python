from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from predicate.agent_runtime import AgentRuntime
from predicate.agents import PredicateBrowserAgent, PredicateBrowserAgentConfig
from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.models import (
    BBox,
    Element,
    Snapshot,
    SnapshotDiagnostics,
    Viewport,
    VisualCues,
)
from predicate.runtime_agent import RuntimeStep
from predicate.verification import AssertContext, AssertOutcome


class MockTracer:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        self.events.append({"type": event_type, "data": data, "step_id": step_id})


class MockBackend:
    def __init__(self) -> None:
        self.mouse_clicks: list[tuple[float, float]] = []

    async def refresh_page_info(self):
        return None

    async def eval(self, expression: str):
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
        _ = text
        return None

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


class TokenProviderStub(LLMProvider):
    def __init__(self, *, model: str = "stub", response: str = "FINISH()"):
        super().__init__(model)
        self._response = response

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        _ = system_prompt, user_prompt, kwargs
        return LLMResponse(
            content=self._response,
            model_name=self.model_name,
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        )

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return self._model_name


def make_snapshot(*, url: str, elements: list[Element], confidence: float | None = None) -> Snapshot:
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


def test_predicate_browser_agent_allows_compact_prompt_builder_override() -> None:
    async def _run() -> None:
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        s0 = make_snapshot(url="https://example.com/start", elements=[make_clickable_element(1)])
        s1 = make_snapshot(url="https://example.com/done", elements=[make_clickable_element(1)])

        async def fake_snapshot(**_kwargs):
            runtime.last_snapshot = snaps.pop(0)
            return runtime.last_snapshot

        snaps = [s0, s1]
        runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

        step = RuntimeStep(goal="Click OK", verifications=[])
        executor = ProviderStub(responses=["CLICK(1)"])

        def builder(
            task_goal: str,
            step_goal: str,
            dom_context: str,
            snap: Snapshot,
            history: str,
        ):
            _ = task_goal, step_goal, dom_context, snap, history
            return ("SYSTEM_CUSTOM", "USER_CUSTOM")

        agent = PredicateBrowserAgent(
            runtime=runtime,
            executor=executor,
            config=PredicateBrowserAgentConfig(compact_prompt_builder=builder),
        )

        out = await agent.step(task_goal="test", step=step)
        assert out.ok is True
        assert executor.calls
        assert "SYSTEM_CUSTOM" in executor.calls[0]["system"]
        assert executor.calls[0]["user"] == "USER_CUSTOM"

    asyncio.run(_run())


def test_predicate_browser_agent_token_usage_is_opt_in_and_best_effort() -> None:
    async def _run() -> None:
        backend = MockBackend()
        tracer = MockTracer()
        runtime = AgentRuntime(backend=backend, tracer=tracer)

        s0 = make_snapshot(url="https://example.com/start", elements=[make_clickable_element(1)])
        async def fake_snapshot(**_kwargs):
            runtime.last_snapshot = s0
            return runtime.last_snapshot
        runtime.snapshot = AsyncMock(side_effect=fake_snapshot)  # type: ignore[method-assign]

        step = RuntimeStep(goal="No-op", verifications=[])
        executor = TokenProviderStub(response="FINISH()")

        agent = PredicateBrowserAgent(
            runtime=runtime,
            executor=executor,
            config=PredicateBrowserAgentConfig(token_usage_enabled=True),
        )

        out = await agent.step(task_goal="test", step=step)
        assert out.ok is True

        usage = agent.get_token_usage()
        assert usage["enabled"] is True
        assert usage["total"]["total_tokens"] >= 18
        assert usage["by_role"]["executor"]["calls"] >= 1

        agent.reset_token_usage()
        usage2 = agent.get_token_usage()
        assert usage2["total"]["total_tokens"] == 0

    asyncio.run(_run())

