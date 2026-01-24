from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .context import ToolContext
from .registry import ToolRegistry


class FileSandbox:
    """Sandboxed file access rooted at a base directory."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        candidate = (self.base_dir / path).resolve()
        if not candidate.is_relative_to(self.base_dir):
            raise ValueError("path escapes sandbox root")
        return candidate

    def read_text(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_text(self, path: str, content: str, *, overwrite: bool = True) -> int:
        target = self._resolve(path)
        if target.exists() and not overwrite:
            raise ValueError("file exists and overwrite is False")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return len(content.encode("utf-8"))

    def append_text(self, path: str, content: str) -> int:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return len(content.encode("utf-8"))

    def replace_text(self, path: str, old: str, new: str) -> int:
        target = self._resolve(path)
        data = target.read_text(encoding="utf-8")
        replaced = data.count(old)
        target.write_text(data.replace(old, new), encoding="utf-8")
        return replaced


class ReadFileInput(BaseModel):
    path: str = Field(..., min_length=1, description="Path relative to sandbox root.")


class ReadFileOutput(BaseModel):
    content: str = Field(..., description="File contents.")


class WriteFileInput(BaseModel):
    path: str = Field(..., min_length=1, description="Path relative to sandbox root.")
    content: str = Field(..., description="Content to write.")
    overwrite: bool = Field(True, description="Whether to overwrite if file exists.")


class WriteFileOutput(BaseModel):
    path: str
    bytes_written: int


class AppendFileInput(BaseModel):
    path: str = Field(..., min_length=1, description="Path relative to sandbox root.")
    content: str = Field(..., description="Content to append.")


class AppendFileOutput(BaseModel):
    path: str
    bytes_written: int


class ReplaceFileInput(BaseModel):
    path: str = Field(..., min_length=1, description="Path relative to sandbox root.")
    old: str = Field(..., description="Text to replace.")
    new: str = Field(..., description="Replacement text.")


class ReplaceFileOutput(BaseModel):
    path: str
    replaced: int


def register_filesystem_tools(
    registry: ToolRegistry, sandbox: FileSandbox | None = None
) -> ToolRegistry:
    """Register sandboxed filesystem tools."""

    def _get_files(ctx: ToolContext | None) -> FileSandbox:
        if ctx is not None:
            return ctx.files
        if sandbox is not None:
            return sandbox
        raise RuntimeError("FileSandbox is required for filesystem tools")

    @registry.tool(
        name="read_file",
        input_model=ReadFileInput,
        output_model=ReadFileOutput,
        description="Read a file from the sandbox.",
    )
    async def read_file(ctx: ToolContext | None, params: ReadFileInput) -> ReadFileOutput:
        files = _get_files(ctx)
        return ReadFileOutput(content=files.read_text(params.path))

    @registry.tool(
        name="write_file",
        input_model=WriteFileInput,
        output_model=WriteFileOutput,
        description="Write a file to the sandbox.",
    )
    async def write_file(
        ctx: ToolContext | None, params: WriteFileInput
    ) -> WriteFileOutput:
        files = _get_files(ctx)
        written = files.write_text(params.path, params.content, overwrite=params.overwrite)
        return WriteFileOutput(path=params.path, bytes_written=written)

    @registry.tool(
        name="append_file",
        input_model=AppendFileInput,
        output_model=AppendFileOutput,
        description="Append text to a file in the sandbox.",
    )
    async def append_file(
        ctx: ToolContext | None, params: AppendFileInput
    ) -> AppendFileOutput:
        files = _get_files(ctx)
        written = files.append_text(params.path, params.content)
        return AppendFileOutput(path=params.path, bytes_written=written)

    @registry.tool(
        name="replace_file",
        input_model=ReplaceFileInput,
        output_model=ReplaceFileOutput,
        description="Replace text in a file in the sandbox.",
    )
    async def replace_file(
        ctx: ToolContext | None, params: ReplaceFileInput
    ) -> ReplaceFileOutput:
        files = _get_files(ctx)
        replaced = files.replace_text(params.path, params.old, params.new)
        return ReplaceFileOutput(path=params.path, replaced=replaced)

    return registry
