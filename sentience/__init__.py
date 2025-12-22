"""
Sentience Python SDK - AI Agent Browser Automation
"""

from .browser import SentienceBrowser
from .models import Snapshot, Element, BBox, Viewport, ActionResult, WaitResult
from .snapshot import snapshot
from .query import query, find
from .actions import click, type_text, press
from .wait import wait_for
from .expect import expect
from .inspector import Inspector, inspect
from .recorder import Recorder, Trace, TraceStep, record
from .generator import ScriptGenerator, generate
from .read import read
from .screenshot import screenshot

__version__ = "0.1.0"

__all__ = [
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
]

