"""
Snapshot formatting utilities for LLM prompts.

Provides functions to convert Sentience snapshots into text format suitable
for LLM consumption.
"""

from typing import List

from ..models import Snapshot


def format_snapshot_for_llm(snap: Snapshot, limit: int = 50) -> str:
    """
    Convert snapshot elements to text format for LLM consumption.

    This is the canonical way Sentience formats DOM state for LLMs.
    The format includes element ID, role, text preview, visual cues,
    position, and importance score.

    Args:
        snap: Snapshot object with elements
        limit: Maximum number of elements to include (default: 50)

    Returns:
        Formatted string with one element per line

    Example:
        >>> snap = snapshot(browser)
        >>> formatted = format_snapshot_for_llm(snap, limit=10)
        >>> print(formatted)
        [1] <button> "Sign In" {PRIMARY,CLICKABLE} @ (100,50) (Imp:10)
        [2] <input> "Email address" @ (100,100) (Imp:8)
        ...
    """
    lines: list[str] = []

    for el in snap.elements[:limit]:
        # Build visual cues string
        cues = []
        if getattr(el.visual_cues, "is_primary", False):
            cues.append("PRIMARY")
        if getattr(el.visual_cues, "is_clickable", False):
            cues.append("CLICKABLE")

        cues_str = f" {{{','.join(cues)}}}" if cues else ""

        # Format text preview (truncate to 50 chars)
        text_preview = el.text or ""
        if len(text_preview) > 50:
            text_preview = text_preview[:50] + "..."

        # Build element line: [ID] <role> "text" {cues} @ (x,y) (Imp:score)
        lines.append(
            f'[{el.id}] <{el.role}> "{text_preview}"{cues_str} '
            f"@ ({int(el.bbox.x)},{int(el.bbox.y)}) (Imp:{el.importance})"
        )

    return "\n".join(lines)
