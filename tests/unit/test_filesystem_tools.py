from __future__ import annotations

from pathlib import Path

import pytest

from sentience.tools import FileSandbox, ToolContext, ToolRegistry, register_filesystem_tools


class RuntimeStub:
    def __init__(self) -> None:
        self.tracer = None
        self.step_id = None

    def capabilities(self):
        return None

    def can(self, _name: str) -> bool:
        return True


def test_file_sandbox_prevents_traversal(tmp_path: Path) -> None:
    sandbox = FileSandbox(tmp_path)
    with pytest.raises(ValueError):
        sandbox.read_text("../secret.txt")


def test_file_sandbox_prefix_edge_case(tmp_path: Path) -> None:
    base = tmp_path / "sandbox"
    sibling = tmp_path / "sandbox2"
    base.mkdir()
    sibling.mkdir()
    sandbox = FileSandbox(base)
    with pytest.raises(ValueError):
        sandbox.read_text("../sandbox2/file.txt")


@pytest.mark.asyncio
async def test_filesystem_tools_read_write_append_replace(tmp_path: Path) -> None:
    registry = ToolRegistry()
    sandbox = FileSandbox(tmp_path)
    ctx = ToolContext(RuntimeStub(), files=sandbox)
    register_filesystem_tools(registry, sandbox)

    await registry.execute("write_file", {"path": "note.txt", "content": "hello"}, ctx=ctx)
    result = await registry.execute("read_file", {"path": "note.txt"}, ctx=ctx)
    assert result.content == "hello"

    await registry.execute("append_file", {"path": "note.txt", "content": " world"}, ctx=ctx)
    result = await registry.execute("read_file", {"path": "note.txt"}, ctx=ctx)
    assert result.content == "hello world"

    replaced = await registry.execute(
        "replace_file", {"path": "note.txt", "old": "world", "new": "there"}, ctx=ctx
    )
    assert replaced.replaced == 1
    result = await registry.execute("read_file", {"path": "note.txt"}, ctx=ctx)
    assert result.content == "hello there"
