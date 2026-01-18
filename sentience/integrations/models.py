"""
Shared typed models for integrations (internal).

These are intentionally small, framework-friendly return types for tool wrappers.
They wrap/derive from existing Sentience SDK types while keeping payloads bounded
and predictable for LLM tool calls.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from sentience.models import BBox


class ElementSummary(BaseModel):
    """A small, stable subset of `sentience.models.Element` suitable for tool returns."""

    id: int
    role: str
    text: str | None = None
    importance: int | None = None
    bbox: BBox | None = None


class BrowserState(BaseModel):
    """
    Minimal browser state for integrations.

    Notes:
    - Keep this payload bounded: prefer `snapshot(limit=50)` and summarize elements.
    - Integrations can extend this in their own packages without changing core SDK.
    """

    url: str
    elements: list[ElementSummary]


class AssertionResult(BaseModel):
    """Framework-friendly assertion/guard result."""

    passed: bool
    reason: str = ""
    details: dict[str, Any] = {}
