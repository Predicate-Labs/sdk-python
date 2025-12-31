"""
Sentience Python SDK - AI Agent Browser Automation
"""

from .actions import click, click_rect, press, type_text
from .agent import SentienceAgent
from .agent_config import AgentConfig

# Agent Layer (Phase 1 & 2)
from .base_agent import BaseAgent
from .browser import SentienceBrowser

# Tracing (v0.12.0+)
from .cloud_tracing import CloudTraceSink, SentienceLogger
from .conversational_agent import ConversationalAgent
from .expect import expect

# Formatting (v0.12.0+)
from .formatting import format_snapshot_for_llm
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
    Cookie,
    Element,
    LocalStorageItem,
    OriginStorage,
    ScreenshotConfig,
    Snapshot,
    SnapshotFilter,
    SnapshotOptions,
    StorageState,
    TextContext,
    TextMatch,
    TextRect,
    TextRectSearchResult,
    TokenStats,
    Viewport,
    ViewportRect,
    WaitResult,
)
from .overlay import clear_overlay, show_overlay
from .query import find, query
from .read import read
from .recorder import Recorder, Trace, TraceStep, record
from .screenshot import screenshot
from .snapshot import snapshot
from .text_search import find_text_rect
from .tracer_factory import SENTIENCE_API_URL, create_tracer
from .tracing import JsonlTraceSink, TraceEvent, Tracer, TraceSink

# Utilities (v0.12.0+)
from .utils import (
    canonical_snapshot_loose,
    canonical_snapshot_strict,
    compute_snapshot_digests,
    save_storage_state,
    sha256_digest,
)
from .wait import wait_for

__version__ = "0.90.15"

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
    "show_overlay",
    "clear_overlay",
    # Text Search
    "find_text_rect",
    "TextRectSearchResult",
    "TextMatch",
    "TextRect",
    "ViewportRect",
    "TextContext",
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
    # Storage State Models (Auth Injection)
    "StorageState",
    "Cookie",
    "LocalStorageItem",
    "OriginStorage",
    # Tracing (v0.12.0+)
    "Tracer",
    "TraceSink",
    "JsonlTraceSink",
    "CloudTraceSink",
    "SentienceLogger",
    "TraceEvent",
    "create_tracer",
    "SENTIENCE_API_URL",
    # Utilities (v0.12.0+)
    "canonical_snapshot_strict",
    "canonical_snapshot_loose",
    "compute_snapshot_digests",
    "sha256_digest",
    "save_storage_state",
    # Formatting (v0.12.0+)
    "format_snapshot_for_llm",
    # Agent Config (v0.12.0+)
    "AgentConfig",
]
