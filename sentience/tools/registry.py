from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolSpec(BaseModel):
    """Definition of a tool with typed input/output schemas."""

    name: str = Field(..., min_length=1, description="Unique tool name.")
    description: str | None = Field(None, description="Human-readable tool description.")
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., Any] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def llm_spec(self) -> dict[str, Any]:
        """Return a normalized tool spec for LLM prompts."""
        return {
            "name": self.name,
            "description": self.description or "",
            "parameters": self.input_model.model_json_schema(),
        }

    def validate_input(self, payload: Any) -> BaseModel:
        """Validate tool input payload."""
        return self.input_model.model_validate(payload)

    def validate_output(self, payload: Any) -> BaseModel:
        """Validate tool output payload."""
        return self.output_model.model_validate(payload)


class ToolRegistry:
    """Registry for tool specs and validation."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolRegistry:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        return self

    def tool(
        self,
        *,
        name: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        description: str | None = None,
    ):
        """Decorator to register a tool handler."""

        def decorator(func: Callable[..., Any]):
            spec = ToolSpec(
                name=name,
                description=description,
                input_model=input_model,
                output_model=output_model,
                handler=func,
            )
            self.register(spec)
            return func

        return decorator

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def llm_tools(self) -> list[dict[str, Any]]:
        return [spec.llm_spec() for spec in self.list()]

    def validate_input(self, name: str, payload: Any) -> BaseModel:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"tool not found: {name}")
        return spec.validate_input(payload)

    def validate_output(self, name: str, payload: Any) -> BaseModel:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"tool not found: {name}")
        return spec.validate_output(payload)

    def validate_call(self, name: str, payload: Any) -> tuple[BaseModel, ToolSpec]:
        """Validate input and return (validated, spec)."""
        validated = self.validate_input(name, payload)
        return validated, self._tools[name]

    async def execute(self, name: str, payload: Any, ctx: Any | None = None) -> BaseModel:
        """Validate inputs, execute handler, validate output."""
        start = time.time()
        validated, spec = self.validate_call(name, payload)
        if spec.handler is None:
            raise ValueError(f"tool has no handler: {name}")
        tracer = None
        step_id = None
        if ctx is not None:
            runtime = getattr(ctx, "runtime", None)
            tracer = getattr(runtime, "tracer", None)
            step_id = getattr(runtime, "step_id", None)
        try:
            result = spec.handler(ctx, validated)
            if inspect.isawaitable(result):
                result = await result
            validated_output = spec.validate_output(result)
            if tracer:
                tracer.emit(
                    "tool_call",
                    data={
                        "tool_name": name,
                        "inputs": validated.model_dump(),
                        "outputs": validated_output.model_dump(),
                        "success": True,
                        "duration_ms": int((time.time() - start) * 1000),
                    },
                    step_id=step_id,
                )
            return validated_output
        except Exception as exc:
            if tracer:
                tracer.emit(
                    "tool_call",
                    data={
                        "tool_name": name,
                        "inputs": validated.model_dump(),
                        "success": False,
                        "error": str(exc),
                        "duration_ms": int((time.time() - start) * 1000),
                    },
                    step_id=step_id,
                )
            raise
