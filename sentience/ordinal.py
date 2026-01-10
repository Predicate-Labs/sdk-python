"""
Phase 3: Ordinal Intent Detection for Semantic Search

This module provides functions to detect ordinal intent in natural language goals
and select elements based on their position within groups.

Ordinal operators supported:
- Position-based: "first", "second", "third", "1st", "2nd", "3rd", etc.
- Relative: "top", "bottom", "last", "next", "previous"
- Numeric: "#1", "#2", "number 1", "item 3"

Example usage:
    from sentience.ordinal import detect_ordinal_intent, select_by_ordinal

    intent = detect_ordinal_intent("click the first search result")
    # OrdinalIntent(kind='nth', n=1, detected=True)

    element = select_by_ordinal(elements, dominant_group_key, intent)
"""

from dataclasses import dataclass
from typing import Literal
import re

from sentience.models import Element


@dataclass
class OrdinalIntent:
    """Detected ordinal intent from a goal string."""

    detected: bool
    kind: Literal["first", "last", "nth", "top_k", "next", "previous"] | None = None
    n: int | None = None  # For "nth" kind: 1-indexed position (1=first, 2=second)
    k: int | None = None  # For "top_k" kind: number of items


# Ordinal word to number mapping
ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "1st": 1,
    "2nd": 2,
    "3rd": 3,
    "4th": 4,
    "5th": 5,
    "6th": 6,
    "7th": 7,
    "8th": 8,
    "9th": 9,
    "10th": 10,
}

# Patterns for detecting ordinal intent
ORDINAL_PATTERNS = [
    # "first", "second", etc.
    (
        r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b",
        "ordinal_word",
    ),
    # "1st", "2nd", "3rd", etc.
    (r"\b(\d+)(st|nd|rd|th)\b", "ordinal_suffix"),
    # "#1", "#2", etc.
    (r"#(\d+)\b", "hash_number"),
    # "number 1", "item 3", "result 5"
    (r"\b(?:number|item|result|option|choice)\s*(\d+)\b", "labeled_number"),
    # "top" (implies first/best)
    (r"\btop\b(?!\s*\d)", "top"),
    # "top 3", "top 5"
    (r"\btop\s+(\d+)\b", "top_k"),
    # "last", "final", "bottom"
    (r"\b(last|final|bottom)\b", "last"),
    # "next", "following"
    (r"\b(next|following)\b", "next"),
    # "previous", "preceding", "prior"
    (r"\b(previous|preceding|prior)\b", "previous"),
]


def detect_ordinal_intent(goal: str) -> OrdinalIntent:
    """
    Detect ordinal intent from a goal string.

    Args:
        goal: Natural language goal (e.g., "click the first search result")

    Returns:
        OrdinalIntent with detected=True if ordinal intent found, False otherwise.

    Examples:
        >>> detect_ordinal_intent("click the first item")
        OrdinalIntent(detected=True, kind='nth', n=1)

        >>> detect_ordinal_intent("select the 3rd option")
        OrdinalIntent(detected=True, kind='nth', n=3)

        >>> detect_ordinal_intent("show top 5 results")
        OrdinalIntent(detected=True, kind='top_k', k=5)

        >>> detect_ordinal_intent("click the last button")
        OrdinalIntent(detected=True, kind='last')

        >>> detect_ordinal_intent("find the submit button")
        OrdinalIntent(detected=False)
    """
    goal_lower = goal.lower()

    for pattern, pattern_type in ORDINAL_PATTERNS:
        match = re.search(pattern, goal_lower, re.IGNORECASE)
        if match:
            if pattern_type == "ordinal_word":
                word = match.group(1).lower()
                n = ORDINAL_WORDS.get(word)
                if n:
                    return OrdinalIntent(detected=True, kind="nth", n=n)

            elif pattern_type == "ordinal_suffix":
                n = int(match.group(1))
                return OrdinalIntent(detected=True, kind="nth", n=n)

            elif pattern_type == "hash_number":
                n = int(match.group(1))
                return OrdinalIntent(detected=True, kind="nth", n=n)

            elif pattern_type == "labeled_number":
                n = int(match.group(1))
                return OrdinalIntent(detected=True, kind="nth", n=n)

            elif pattern_type == "top":
                # "top" without a number means "first/best"
                return OrdinalIntent(detected=True, kind="first")

            elif pattern_type == "top_k":
                k = int(match.group(1))
                return OrdinalIntent(detected=True, kind="top_k", k=k)

            elif pattern_type == "last":
                return OrdinalIntent(detected=True, kind="last")

            elif pattern_type == "next":
                return OrdinalIntent(detected=True, kind="next")

            elif pattern_type == "previous":
                return OrdinalIntent(detected=True, kind="previous")

    return OrdinalIntent(detected=False)


def select_by_ordinal(
    elements: list[Element],
    dominant_group_key: str | None,
    intent: OrdinalIntent,
    current_element_id: int | None = None,
) -> Element | list[Element] | None:
    """
    Select element(s) from a list based on ordinal intent.

    Uses the dominant_group_key to filter to the "main content" group,
    then selects by group_index based on the ordinal intent.

    Args:
        elements: List of elements with group_key and group_index populated
        dominant_group_key: The most common group key (main content group)
        intent: Detected ordinal intent
        current_element_id: Current element ID (for next/previous navigation)

    Returns:
        Single Element for nth/first/last, list of Elements for top_k,
        or None if no matching element found.

    Examples:
        >>> intent = OrdinalIntent(detected=True, kind='nth', n=1)
        >>> element = select_by_ordinal(elements, "x5-w2-h1", intent)
        # Returns element with group_key="x5-w2-h1" and group_index=0
    """
    if not intent.detected:
        return None

    # Filter to dominant group if available
    if dominant_group_key:
        group_elements = [e for e in elements if e.group_key == dominant_group_key]
    else:
        # Fallback: use all elements with group_index
        group_elements = [e for e in elements if e.group_index is not None]

    if not group_elements:
        return None

    # Sort by group_index to ensure correct ordering
    group_elements.sort(key=lambda e: e.group_index if e.group_index is not None else 0)

    if intent.kind == "first" or (intent.kind == "nth" and intent.n == 1):
        # First element (group_index=0)
        return group_elements[0] if group_elements else None

    elif intent.kind == "nth" and intent.n is not None:
        # Nth element (1-indexed, so n=2 means group_index=1)
        target_index = intent.n - 1
        if 0 <= target_index < len(group_elements):
            return group_elements[target_index]
        return None

    elif intent.kind == "last":
        # Last element
        return group_elements[-1] if group_elements else None

    elif intent.kind == "top_k" and intent.k is not None:
        # Top K elements
        return group_elements[: intent.k]

    elif intent.kind == "next" and current_element_id is not None:
        # Next element after current
        for i, elem in enumerate(group_elements):
            if elem.id == current_element_id and i + 1 < len(group_elements):
                return group_elements[i + 1]
        return None

    elif intent.kind == "previous" and current_element_id is not None:
        # Previous element before current
        for i, elem in enumerate(group_elements):
            if elem.id == current_element_id and i > 0:
                return group_elements[i - 1]
        return None

    return None


def boost_ordinal_elements(
    elements: list[Element],
    dominant_group_key: str | None,
    intent: OrdinalIntent,
    boost_factor: int = 10000,
) -> list[Element]:
    """
    Boost the importance of elements matching ordinal intent.

    This is useful for integrating ordinal selection with existing
    importance-based ranking. Elements matching the ordinal intent
    get a significant importance boost.

    Args:
        elements: List of elements (not modified)
        dominant_group_key: The most common group key
        intent: Detected ordinal intent
        boost_factor: Amount to add to importance (default: 10000)

    Returns:
        A new list with copies of elements, with boosted importance for matches.
    """
    if not intent.detected or not dominant_group_key:
        return [e.model_copy() for e in elements]

    target = select_by_ordinal(elements, dominant_group_key, intent)

    if target is None:
        return [e.model_copy() for e in elements]

    # Handle single element or list
    if isinstance(target, list):
        target_ids = {e.id for e in target}
    else:
        target_ids = {target.id}

    # Create copies and boost matching elements
    result = []
    for elem in elements:
        copy = elem.model_copy()
        if copy.id in target_ids:
            copy.importance = (copy.importance or 0) + boost_factor
        result.append(copy)

    return result
