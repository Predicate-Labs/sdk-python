from __future__ import annotations

import asyncio
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

    def __init__(self, runtime: AgentRuntime, *, auto_step: bool = True) -> None:
        self.runtime = runtime
        self._step_open = False
        self._auto_step = bool(auto_step)
        self._auto_opened_step = False
        self._auto_opened_step_id: str | None = None

    def _schedule_close_auto_step(self) -> None:
        """
        Best-effort: close an auto-opened step without forcing callers to await.
        """
        if not (self._step_open and self._auto_opened_step):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.end_step())

    @classmethod
    def attach(
        cls,
        page: Page,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        predicate_api_key: str | None = None,
        sentience_api_key: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> SentienceDebugger:
        runtime = AgentRuntime.from_playwright_page(
            page=page,
            tracer=tracer,
            snapshot_options=snapshot_options,
            predicate_api_key=predicate_api_key,
            sentience_api_key=sentience_api_key,
            tool_registry=tool_registry,
        )
        return cls(runtime=runtime)

    def begin_step(self, goal: str, step_index: int | None = None) -> str:
        # If we previously auto-opened a verification step, close it before starting a real step.
        if self._step_open and self._auto_opened_step:
            self._schedule_close_auto_step()
            self._auto_opened_step = False
            self._auto_opened_step_id = None
        self._step_open = True
        return self.runtime.begin_step(goal, step_index=step_index)

    async def end_step(self, **kwargs: Any) -> dict[str, Any]:
        self._step_open = False
        self._auto_opened_step = False
        self._auto_opened_step_id = None
        return await self.runtime.emit_step_end(**kwargs)

    @asynccontextmanager
    async def step(self, goal: str, step_index: int | None = None) -> AsyncIterator[None]:
        # Async form can safely close any auto-opened step before starting.
        if self._step_open and self._auto_opened_step:
            await self.end_step()
        self.begin_step(goal, step_index=step_index)
        try:
            yield
        finally:
            await self.end_step()

    async def snapshot(self, **kwargs: Any):
        return await self.runtime.snapshot(**kwargs)

    async def record_action(self, action: str, *, url: str | None = None) -> None:
        """
        Sidecar helper: let the host framework report the action it performed.

        This improves trace readability and (when artifacts are enabled) enriches the action timeline.
        """
        await self.runtime.record_action(action, url=url)

    def check(self, predicate, label: str, required: bool = False):
        if not self._step_open:
            if not self._auto_step:
                raise RuntimeError(
                    f"No active step. Call dbg.begin_step(...) or use 'async with dbg.step(...)' before check(label={label!r})."
                )
            self.begin_step(f"verify:{label}")
            self._auto_opened_step = True
            self._auto_opened_step_id = getattr(self.runtime, "step_id", None)

        base = self.runtime.check(predicate, label, required=required)

        # Auto-close auto-opened verification steps after the check completes.
        if not self._auto_opened_step:
            return base

        dbg = self
        opened_step_id = self._auto_opened_step_id

        class _AutoCloseAssertionHandle:
            def __init__(self, inner):
                self._inner = inner

            def once(self) -> bool:
                ok = self._inner.once()
                if (
                    dbg._step_open
                    and dbg._auto_opened_step
                    and (
                        opened_step_id is None
                        or getattr(dbg.runtime, "step_id", None) == opened_step_id
                    )
                ):
                    dbg._schedule_close_auto_step()
                return ok

            async def eventually(self, **kwargs: Any) -> bool:
                ok = await self._inner.eventually(**kwargs)
                if (
                    dbg._step_open
                    and dbg._auto_opened_step
                    and (
                        opened_step_id is None
                        or getattr(dbg.runtime, "step_id", None) == opened_step_id
                    )
                ):
                    await dbg.end_step()
                return ok

        return _AutoCloseAssertionHandle(base)
