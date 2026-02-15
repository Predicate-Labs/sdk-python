from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.models import BBox, Element, Snapshot, Viewport, VisualCues
from predicate.runtime_agent import RuntimeAgent, RuntimeStep


class _BackendStub:
    def __init__(self) -> None:
        self._url = "https://example.com/"
        self.mouse_clicks: list[tuple[float, float]] = []
        self.typed: list[str] = []

    async def get_url(self) -> str:
        return self._url

    async def eval(self, expression: str) -> Any:
        # Used for canvas detection + keypress best-effort; keep simple.
        if "querySelectorAll('canvas')" in expression:
            return 0
        return None

    async def screenshot_png(self) -> bytes:
        return b"png"

    async def wait_ready_state(self, state: str = "interactive", timeout_ms: int = 15000) -> None:
        _ = state, timeout_ms
        return None

    async def mouse_click(self, x: float, y: float, button: str = "left", click_count: int = 1) -> None:
        _ = button, click_count
        self.mouse_clicks.append((float(x), float(y)))

    async def mouse_move(self, x: float, y: float) -> None:
        _ = x, y
        return None

    async def type_text(self, text: str) -> None:
        self.typed.append(str(text))


@dataclass
class _RuntimeStub:
    backend: _BackendStub
    last_snapshot: Snapshot | None = None
    recorded_actions: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.recorded_actions = []

    async def snapshot(
        self,
        goal: str,
        *,
        limit: int,
        max_attempts: int = 3,
        min_confidence: float | None = None,
        min_actionables: int | None = None,
    ) -> Snapshot:
        _ = goal, limit, max_attempts, min_confidence, min_actionables
        snap = Snapshot(
            status="success",
            url="https://example.com/",
            viewport=Viewport(width=1200, height=800),
            elements=[
                Element(
                    id=1,
                    bbox=BBox(x=10, y=10, width=100, height=20),
                    text="Click me",
                    role="button",
                    importance=100,
                    visual_cues=VisualCues(
                        is_primary=True,
                        is_clickable=True,
                        background_color_name=None,
                    ),
                    in_viewport=True,
                    is_occluded=False,
                )
            ],
        )
        self.last_snapshot = snap
        return snap

    async def get_url(self) -> str:
        return await self.backend.get_url()

    async def record_action(self, action: str, url: str | None = None) -> None:
        _ = url
        self.recorded_actions.append(action)


class _ProviderStub(LLMProvider):
    def __init__(self, *, response: str, model: str = "stub") -> None:
        super().__init__(model)
        self._response = response

    def supports_json_mode(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        _ = system_prompt, user_prompt, kwargs
        return LLMResponse(content=self._response, model_name=self.model_name)

    @property
    def model_name(self) -> str:
        return self._model_name


def test_runtime_agent_act_once_does_not_require_step_lifecycle() -> None:
    async def _run() -> None:
        backend = _BackendStub()
        runtime = _RuntimeStub(backend=backend)
        llm = _ProviderStub(response="CLICK(1)")
        agent = RuntimeAgent(runtime=runtime, executor=llm)

        action, snap = await agent.act_once_with_snapshot(
            task_goal="Do a thing",
            step=RuntimeStep(goal="Click the button"),
            allow_vision_fallback=False,
        )

        assert action.strip().upper().startswith("CLICK(")
        assert snap is runtime.last_snapshot
        assert runtime.recorded_actions == ["CLICK(1)"]
        assert len(backend.mouse_clicks) == 1

    asyncio.run(_run())

