from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from predicate.tools import (
    ToolContext,
    ToolRegistry,
    ToolSpec,
    UnsupportedCapabilityError,
    register_default_tools,
)


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    echoed: str


def test_register_and_list_tools() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(
        name="echo",
        description="Echo a message",
        input_model=EchoInput,
        output_model=EchoOutput,
    )
    registry.register(spec)
    assert registry.get("echo") is spec
    assert len(registry.list()) == 1


def test_validate_input_and_output() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="Echo a message",
            input_model=EchoInput,
            output_model=EchoOutput,
        )
    )

    validated = registry.validate_input("echo", {"message": "hi"})
    assert isinstance(validated, EchoInput)
    assert validated.message == "hi"

    out = registry.validate_output("echo", {"echoed": "hi"})
    assert isinstance(out, EchoOutput)
    assert out.echoed == "hi"

    with pytest.raises(ValidationError):
        registry.validate_input("echo", {"message": 123})


def test_llm_spec_generation() -> None:
    registry = ToolRegistry()

    @registry.tool(
        name="echo",
        input_model=EchoInput,
        output_model=EchoOutput,
        description="Echo a message",
    )
    def _echo(_ctx, params: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=params.message)

    tools = registry.llm_tools()
    assert tools[0]["name"] == "echo"
    assert tools[0]["description"] == "Echo a message"
    assert "parameters" in tools[0]


def test_register_default_tools_adds_core_tools() -> None:
    registry = ToolRegistry()

    class RuntimeStub:
        async def snapshot(self, **_kwargs):
            return None

        last_snapshot = None
        backend = None

    ctx = ToolContext(RuntimeStub())
    register_default_tools(registry, ctx)
    names = {spec.name for spec in registry.list()}
    assert {
        "snapshot_state",
        "click",
        "type",
        "scroll",
        "scroll_to_element",
        "click_rect",
        "press",
        "evaluate_js",
        "grant_permissions",
        "clear_permissions",
        "set_geolocation",
    } <= names


@pytest.mark.asyncio
async def test_registry_execute_validates_and_runs() -> None:
    registry = ToolRegistry()

    class TracerStub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
            self.events.append({"type": event_type, "data": data, "step_id": step_id})

    class RuntimeStub:
        def __init__(self) -> None:
            self.tracer = TracerStub()
            self.step_id = "step-1"

        def capabilities(self):
            return None

        def can(self, _name: str) -> bool:
            return True

    runtime = RuntimeStub()
    ctx = ToolContext(runtime)

    @registry.tool(
        name="echo",
        input_model=EchoInput,
        output_model=EchoOutput,
        description="Echo",
    )
    async def _echo(_ctx, params: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=params.message)

    result = await registry.execute("echo", {"message": "hi"}, ctx=ctx)
    assert isinstance(result, EchoOutput)
    assert result.echoed == "hi"
    assert runtime.tracer.events[0]["type"] == "tool_call"
    assert runtime.tracer.events[0]["data"]["success"] is True


def test_tool_context_require_raises_on_missing_capability() -> None:
    class RuntimeStub:
        def capabilities(self):
            return None

        def can(self, _name: str) -> bool:
            return False

    ctx = ToolContext(RuntimeStub())
    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        ctx.require("tabs")
    assert excinfo.value.error == "unsupported_capability"


@pytest.mark.asyncio
async def test_tool_call_emits_error_on_failure() -> None:
    registry = ToolRegistry()

    class TracerStub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
            self.events.append({"type": event_type, "data": data, "step_id": step_id})

    class RuntimeStub:
        def __init__(self) -> None:
            self.tracer = TracerStub()
            self.step_id = "step-1"

        def capabilities(self):
            return None

        def can(self, _name: str) -> bool:
            return True

    runtime = RuntimeStub()
    ctx = ToolContext(runtime)

    @registry.tool(
        name="boom",
        input_model=EchoInput,
        output_model=EchoOutput,
        description="Boom",
    )
    async def _boom(_ctx, _params: EchoInput) -> EchoOutput:
        raise RuntimeError("bad")

    with pytest.raises(RuntimeError, match="bad"):
        await registry.execute("boom", {"message": "x"}, ctx=ctx)

    assert runtime.tracer.events[0]["type"] == "tool_call"
    assert runtime.tracer.events[0]["data"]["success"] is False
    assert "error" in runtime.tracer.events[0]["data"]


@pytest.mark.asyncio
async def test_default_tools_capability_checks() -> None:
    registry = ToolRegistry()

    class RuntimeStub:
        def __init__(self) -> None:
            self.tracer = None
            self.step_id = None

        def capabilities(self):
            return None

        def can(self, name: str) -> bool:
            return name not in {"keyboard", "evaluate_js", "permissions"}

        async def snapshot(self, **_kwargs):
            return None

        last_snapshot = None
        backend = None

    ctx = ToolContext(RuntimeStub())
    register_default_tools(registry, ctx)

    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        await registry.execute("press", {"key": "Enter"}, ctx=ctx)
    assert excinfo.value.error == "unsupported_capability"

    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        await registry.execute(
            "scroll_to_element",
            {"element_id": 1, "behavior": "instant", "block": "center"},
            ctx=ctx,
        )
    assert excinfo.value.error == "unsupported_capability"

    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        await registry.execute(
            "grant_permissions",
            {"permissions": ["geolocation"]},
            ctx=ctx,
        )
    assert excinfo.value.error == "unsupported_capability"
