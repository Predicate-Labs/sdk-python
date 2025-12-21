"""
Sentience Python SDK - AI Agent Browser Automation
"""

from .browser import SentienceBrowser
from .models import Snapshot, Element, BBox, Viewport, ActionResult, WaitResult
from .query import query, find
from .actions import click, type_text, press
from .wait import wait_for
from .expect import expect

__version__ = "0.1.0"

__all__ = [
    "SentienceBrowser",
    "Snapshot",
    "Element",
    "BBox",
    "Viewport",
    "ActionResult",
    "WaitResult",
    "query",
    "find",
    "click",
    "type_text",
    "press",
    "wait_for",
    "expect",
]

