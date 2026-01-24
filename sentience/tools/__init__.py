"""
Tool registry for LLM-callable tools.
"""

from .context import BackendCapabilities, ToolContext, UnsupportedCapabilityError
from .defaults import register_default_tools
from .filesystem import FileSandbox, register_filesystem_tools
from .registry import ToolRegistry, ToolSpec

__all__ = [
    "BackendCapabilities",
    "FileSandbox",
    "ToolContext",
    "ToolRegistry",
    "ToolSpec",
    "UnsupportedCapabilityError",
    "register_default_tools",
    "register_filesystem_tools",
]
