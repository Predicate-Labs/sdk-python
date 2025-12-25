"""
Sentience Python SDK - AI Agent Browser Automation
"""

from .actions import click, click_rect, press, type_text
from .agent import SentienceAgent

# Agent Layer (Phase 1 & 2)
from .base_agent import BaseAgent
from .browser import SentienceBrowser
from .conversational_agent import ConversationalAgent
from .expect import expect
from .generator import ScriptGenerator, generate
from .inspector import Inspector, inspect
from .llm_provider import (
    AnthropicProvider,
    LLMProvider,
    LLMResponse,
    LocalLLMProvider,
    OpenAIProvider,
)
from .models import (  # Agent Layer Models
    ActionHistory,
    ActionResult,
    ActionTokenUsage,
    AgentActionResult,
    BBox,
    Element,
    ScreenshotConfig,
    Snapshot,
    SnapshotFilter,
    SnapshotOptions,
    TokenStats,
    Viewport,
    WaitResult,
)
from .query import find, query
from .read import read
from .recorder import Recorder, Trace, TraceStep, record
from .screenshot import screenshot
from .snapshot import snapshot
from .wait import wait_for

__version__ = "0.10.7"

__all__ = [
    # Core SDK
    "SentienceBrowser",
    "Snapshot",
    "Element",
    "BBox",
    "Viewport",
    "ActionResult",
    "WaitResult",
    "snapshot",
    "query",
    "find",
    "click",
    "type_text",
    "press",
    "click_rect",
    "wait_for",
    "expect",
    "Inspector",
    "inspect",
    "Recorder",
    "Trace",
    "TraceStep",
    "record",
    "ScriptGenerator",
    "generate",
    "read",
    "screenshot",
    # Agent Layer (Phase 1 & 2)
    "BaseAgent",
    "LLMProvider",
    "LLMResponse",
    "OpenAIProvider",
    "AnthropicProvider",
    "LocalLLMProvider",
    "SentienceAgent",
    "ConversationalAgent",
    # Agent Layer Models
    "AgentActionResult",
    "TokenStats",
    "ActionHistory",
    "ActionTokenUsage",
    "SnapshotOptions",
    "SnapshotFilter",
    "ScreenshotConfig",
]
