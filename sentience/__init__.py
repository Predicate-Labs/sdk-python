"""
Sentience Python SDK - AI Agent Browser Automation
"""

from .browser import SentienceBrowser
from .models import (
    Snapshot,
    Element,
    BBox,
    Viewport,
    ActionResult,
    WaitResult,
    # Agent Layer Models
    AgentActionResult,
    TokenStats,
    ActionHistory,
    ActionTokenUsage,
    SnapshotOptions,
    SnapshotFilter,
    ScreenshotConfig
)
from .snapshot import snapshot
from .query import query, find
from .actions import click, type_text, press, click_rect
from .wait import wait_for
from .expect import expect
from .inspector import Inspector, inspect
from .recorder import Recorder, Trace, TraceStep, record
from .generator import ScriptGenerator, generate
from .read import read
from .screenshot import screenshot

# Agent Layer (Phase 1 & 2)
from .base_agent import BaseAgent
from .llm_provider import LLMProvider, LLMResponse, OpenAIProvider, AnthropicProvider, LocalLLMProvider
from .agent import SentienceAgent
from .conversational_agent import ConversationalAgent

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

