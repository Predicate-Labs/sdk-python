from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from .agent_runtime import AgentRuntime
from .models import SnapshotOptions
from .tools import ToolRegistry

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from playwright.async_api import Page

    from .tracing import Tracer
else:  # pragma: no cover - avoid optional runtime imports
    Page = Any  # type: ignore
    Tracer = Any  # type: ignore


class SentienceDebugger:
    """
    Verifier-only sidecar wrapper around AgentRuntime.
    """

    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime
        self._step_open = False

    @classmethod
    def attach(
        cls,
        page: Page,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> SentienceDebugger:
        runtime = AgentRuntime.from_playwright_page(
            page=page,
            tracer=tracer,
            snapshot_options=snapshot_options,
            sentience_api_key=sentience_api_key,
            tool_registry=tool_registry,
        )
        return cls(runtime=runtime)

    def begin_step(self, goal: str, step_index: int | None = None) -> str:
        self._step_open = True
        return self.runtime.begin_step(goal, step_index=step_index)

    async def end_step(self, **kwargs: Any) -> dict[str, Any]:
        self._step_open = False
        return await self.runtime.emit_step_end(**kwargs)

    @asynccontextmanager
    async def step(self, goal: str, step_index: int | None = None) -> AsyncIterator[None]:
        self.begin_step(goal, step_index=step_index)
        try:
            yield
        finally:
            await self.end_step()

    async def snapshot(self, **kwargs: Any):
        return await self.runtime.snapshot(**kwargs)

    def check(self, predicate, label: str, required: bool = False):
        if not self._step_open:
            self.begin_step(f"verify:{label}")
        return self.runtime.check(predicate, label, required=required)
