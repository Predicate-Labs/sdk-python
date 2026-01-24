from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..agent_runtime import AgentRuntime

from .filesystem import FileSandbox


class BackendCapabilities(BaseModel):
    """Best-effort backend capability flags."""

    tabs: bool = False
    evaluate_js: bool = False
    downloads: bool = False
    filesystem_tools: bool = False
    keyboard: bool = False


class UnsupportedCapabilityError(RuntimeError):
    """Structured error for unsupported capabilities."""

    def __init__(self, capability: str, detail: str | None = None) -> None:
        msg = detail or f"{capability} not supported by backend"
        super().__init__(msg)
        self.error = "unsupported_capability"
        self.detail = msg
        self.capability = capability


class ToolContext:
    """Context passed to tool handlers."""

    def __init__(
        self,
        runtime: "AgentRuntime",
        files: FileSandbox | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self.runtime = runtime
        if files is None:
            root = base_dir or (Path.cwd() / ".sentience" / "files")
            files = FileSandbox(root)
        self.files = files

    def capabilities(self) -> BackendCapabilities:
        return self.runtime.capabilities()

    def can(self, name: str) -> bool:
        return self.runtime.can(name)

    def require(self, name: str) -> None:
        if not self.can(name):
            raise UnsupportedCapabilityError(name)
