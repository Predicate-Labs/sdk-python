"""
Element filtering utilities for agent-based element selection.

This module provides centralized element filtering logic to reduce duplication
across agent implementations.
"""

from typing import Optional

from .models import Element, Snapshot


class ElementFilter:
    """
    Centralized element filtering logic for agent-based element selection.

    Provides static methods for filtering elements based on:
    - Importance scores
    - Goal-based keyword matching
    - Role and visual properties
    """

    # Common stopwords for keyword extraction
    STOPWORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
    }

    @staticmethod
    def filter_by_importance(
        snapshot: Snapshot,
        max_elements: int = 50,
    ) -> list[Element]:
        """
        Filter elements by importance score (simple top-N selection).

        Args:
            snapshot: Current page snapshot
            max_elements: Maximum number of elements to return

        Returns:
            Top N elements sorted by importance score
        """
        elements = snapshot.elements
        # Elements are already sorted by importance in snapshot
        return elements[:max_elements]

    @staticmethod
    def filter_by_goal(
        snapshot: Snapshot,
        goal: Optional[str],
        max_elements: int = 50,
    ) -> list[Element]:
        """
        Filter elements from snapshot based on goal context.

        Applies goal-based keyword matching to boost relevant elements
        and filters out irrelevant ones.

        Args:
            snapshot: Current page snapshot
            goal: User's goal (can inform filtering)
            max_elements: Maximum number of elements to return

        Returns:
            Filtered list of elements sorted by boosted importance score
        """
        elements = snapshot.elements

        # If no goal provided, return all elements (up to limit)
        if not goal:
            return elements[:max_elements]

        goal_lower = goal.lower()

        # Extract keywords from goal
        keywords = ElementFilter._extract_keywords(goal_lower)

        # Boost elements matching goal keywords
        scored_elements = []
        for el in elements:
            score = el.importance

            # Boost if element text matches goal
            if el.text and any(kw in el.text.lower() for kw in keywords):
                score += 0.3

            # Boost if role matches goal intent
            if "click" in goal_lower and el.visual_cues.is_clickable:
                score += 0.2
            if "type" in goal_lower and el.role in ["textbox", "searchbox"]:
                score += 0.2
            if "search" in goal_lower:
                # Filter out non-interactive elements for search tasks
                if el.role in ["link", "img"] and not el.visual_cues.is_primary:
                    score -= 0.5

            scored_elements.append((score, el))

        # Re-sort by boosted score
        scored_elements.sort(key=lambda x: x[0], reverse=True)
        elements = [el for _, el in scored_elements]

        return elements[:max_elements]

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """
        Extract meaningful keywords from goal text.

        Args:
            text: Text to extract keywords from

        Returns:
            List of keywords (non-stopwords, length > 2)
        """
        words = text.split()
        return [w for w in words if w not in ElementFilter.STOPWORDS and len(w) > 2]
