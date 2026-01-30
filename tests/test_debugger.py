from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class MockRuntime:
    def __init__(self) -> None:
        self.begin_step = MagicMock(return_value="step-1")
        self.emit_step_end = AsyncMock(return_value={"ok": True})
        self.check = MagicMock(return_value="check-handle")


class MockTracer:
    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        pass


@pytest.mark.asyncio
async def test_attach_uses_runtime_factory() -> None:
    mock_page = MagicMock()
    tracer = MockTracer()
    runtime = MockRuntime()

    with patch(
        "sentience.debugger.AgentRuntime.from_playwright_page", return_value=runtime
    ) as mock_factory:
        from sentience.debugger import SentienceDebugger

        debugger = SentienceDebugger.attach(page=mock_page, tracer=tracer)

    mock_factory.assert_called_once_with(
        page=mock_page,
        tracer=tracer,
        snapshot_options=None,
        sentience_api_key=None,
        tool_registry=None,
    )
    assert debugger.runtime is runtime


@pytest.mark.asyncio
async def test_step_context_calls_begin_and_emit() -> None:
    runtime = MockRuntime()

    from sentience.debugger import SentienceDebugger

    debugger = SentienceDebugger(runtime=runtime)

    async with debugger.step("verify-cart"):
        pass

    runtime.begin_step.assert_called_once_with("verify-cart", step_index=None)
    runtime.emit_step_end.assert_awaited_once()


def test_check_auto_opens_step_when_missing() -> None:
    runtime = MockRuntime()

    from sentience.debugger import SentienceDebugger

    debugger = SentienceDebugger(runtime=runtime)
    predicate = MagicMock()

    handle = debugger.check(predicate=predicate, label="has_cart", required=True)

    runtime.begin_step.assert_called_once_with("verify:has_cart", step_index=None)
    runtime.check.assert_called_once_with(predicate, "has_cart", required=True)
    assert handle == "check-handle"
