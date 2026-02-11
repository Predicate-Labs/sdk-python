"""
Element query builders for assertion DSL.

This module provides the E() query builder and dominant-group list operations
for creating element queries that compile to existing Predicates.

Key classes:
- ElementQuery: Pure data object for filtering elements (E())
- ListQuery: Query over dominant-group elements (in_dominant_list())
- MultiQuery: Represents multiple elements from ListQuery.top(n)

All queries work with existing Snapshot fields only:
    id, tag, role, text (text_norm), bbox, doc_y, group_key, group_index,
    dominant_group_key, in_viewport, is_occluded, href
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Element, Snapshot


@dataclass
class ElementQuery:
    """
    Pure query object for filtering elements.

    This is the data representation of an E() call. It does not execute
    anything - it just stores the filter criteria.

    Example:
        E(role="button", text_contains="Save")
        E(role="link", href_contains="/cart")
        E(in_viewport=True, occluded=False)
    """

    role: str | None = None
    name: str | None = None  # Alias for text matching (best-effort)
    text: str | None = None  # Exact match against text
    text_contains: str | None = None  # Substring match
    href_contains: str | None = None  # Substring against href
    in_viewport: bool | None = None
    occluded: bool | None = None
    group: str | None = None  # Exact match against group_key
    in_dominant_group: bool | None = None  # True => in dominant group

    # Internal: for ordinal selection from ListQuery
    _group_index: int | None = field(default=None, repr=False)
    _from_dominant_list: bool = field(default=False, repr=False)

    def matches(self, element: Element, snapshot: Snapshot | None = None) -> bool:
        """
        Check if element matches this query criteria.

        Args:
            element: Element to check
            snapshot: Snapshot (needed for dominant_group_key comparison)

        Returns:
            True if element matches all criteria
        """
        # Role filter
        if self.role is not None:
            if element.role != self.role:
                return False

        # Text exact match (name is alias for text)
        text_to_match = self.text or self.name
        if text_to_match is not None:
            element_text = element.text or ""
            if element_text != text_to_match:
                return False

        # Text contains (substring, case-insensitive)
        if self.text_contains is not None:
            element_text = element.text or ""
            if self.text_contains.lower() not in element_text.lower():
                return False

        # Href contains (substring)
        if self.href_contains is not None:
            element_href = element.href or ""
            if self.href_contains.lower() not in element_href.lower():
                return False

        # In viewport filter
        if self.in_viewport is not None:
            if element.in_viewport != self.in_viewport:
                return False

        # Occluded filter
        if self.occluded is not None:
            if element.is_occluded != self.occluded:
                return False

        # Group key exact match
        if self.group is not None:
            if element.group_key != self.group:
                return False

        # In dominant group check
        if self.in_dominant_group is not None:
            if self.in_dominant_group:
                # Element must be in dominant group
                if snapshot is None:
                    return False
                if element.group_key != snapshot.dominant_group_key:
                    return False
            else:
                # Element must NOT be in dominant group
                if snapshot is not None and element.group_key == snapshot.dominant_group_key:
                    return False

        # Group index filter (from ListQuery.nth())
        if self._group_index is not None:
            if element.group_index != self._group_index:
                return False

        # Dominant list filter (from in_dominant_list())
        if self._from_dominant_list:
            if snapshot is None:
                return False
            if element.group_key != snapshot.dominant_group_key:
                return False

        return True

    def find_all(self, snapshot: Snapshot) -> list[Element]:
        """
        Find all elements matching this query in the snapshot.

        Args:
            snapshot: Snapshot to search

        Returns:
            List of matching elements, sorted by doc_y (top to bottom)
        """
        matches = [el for el in snapshot.elements if self.matches(el, snapshot)]
        # Sort by doc_y for consistent ordering (top to bottom)
        matches.sort(key=lambda el: el.doc_y if el.doc_y is not None else el.bbox.y)
        return matches

    def find_first(self, snapshot: Snapshot) -> Element | None:
        """
        Find first matching element.

        Args:
            snapshot: Snapshot to search

        Returns:
            First matching element or None
        """
        matches = self.find_all(snapshot)
        return matches[0] if matches else None


def E(
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    text_contains: str | None = None,
    href_contains: str | None = None,
    in_viewport: bool | None = None,
    occluded: bool | None = None,
    group: str | None = None,
    in_dominant_group: bool | None = None,
) -> ElementQuery:
    """
    Create an element query.

    This is the main entry point for building element queries.
    It returns a pure data object that can be used with expect().

    Args:
        role: ARIA role to match (e.g., "button", "textbox", "link")
        name: Text to match exactly (alias for text, best-effort)
        text: Exact text match against text_norm
        text_contains: Substring match against text_norm (case-insensitive)
        href_contains: Substring match against href (case-insensitive)
        in_viewport: Filter by viewport visibility
        occluded: Filter by occlusion state
        group: Exact match against group_key
        in_dominant_group: True = must be in dominant group

    Returns:
        ElementQuery object

    Example:
        E(role="button", text_contains="Save")
        E(role="link", href_contains="/checkout")
        E(in_viewport=True, occluded=False)
    """
    return ElementQuery(
        role=role,
        name=name,
        text=text,
        text_contains=text_contains,
        href_contains=href_contains,
        in_viewport=in_viewport,
        occluded=occluded,
        group=group,
        in_dominant_group=in_dominant_group,
    )


# Convenience factory methods on E
class _EFactory:
    """Factory class providing convenience methods for common queries."""

    def __call__(
        self,
        role: str | None = None,
        name: str | None = None,
        text: str | None = None,
        text_contains: str | None = None,
        href_contains: str | None = None,
        in_viewport: bool | None = None,
        occluded: bool | None = None,
        group: str | None = None,
        in_dominant_group: bool | None = None,
    ) -> ElementQuery:
        """Create an element query."""
        return E(
            role=role,
            name=name,
            text=text,
            text_contains=text_contains,
            href_contains=href_contains,
            in_viewport=in_viewport,
            occluded=occluded,
            group=group,
            in_dominant_group=in_dominant_group,
        )

    def submit(self) -> ElementQuery:
        """
        Query for submit-like buttons.

        Matches buttons with text like "Submit", "Save", "Continue", etc.
        """
        # This is a heuristic query - matches common submit button patterns
        return ElementQuery(role="button", text_contains="submit")

    def search_box(self) -> ElementQuery:
        """
        Query for search input boxes.

        Matches textbox/combobox with search-related names.
        """
        return ElementQuery(role="textbox", name="search")

    def link(self, text_contains: str | None = None) -> ElementQuery:
        """
        Query for links with optional text filter.

        Args:
            text_contains: Optional text substring to match
        """
        return ElementQuery(role="link", text_contains=text_contains)


@dataclass
class MultiQuery:
    """
    Represents multiple elements from a dominant list query.

    Created by ListQuery.top(n) to represent the first n elements
    in a dominant group.

    Example:
        in_dominant_list().top(5)  # First 5 items in dominant group
    """

    limit: int
    _parent_list_query: ListQuery | None = field(default=None, repr=False)

    def any_text_contains(self, text: str) -> _MultiTextPredicate:
        """
        Create a predicate that checks if any element's text contains the substring.

        Args:
            text: Substring to search for

        Returns:
            Predicate that can be used with expect()
        """
        return _MultiTextPredicate(
            multi_query=self,
            text=text,
            check_type="any_contains",
        )


@dataclass
class _MultiTextPredicate:
    """
    Internal predicate for MultiQuery text checks.

    Used by expect() to evaluate multi-element text assertions.
    """

    multi_query: MultiQuery
    text: str
    check_type: str  # "any_contains", etc.


@dataclass
class ListQuery:
    """
    Query over elements in the dominant group.

    Provides ordinal access to dominant-group elements via .nth(k)
    and range access via .top(n).

    Created by in_dominant_list().

    Example:
        in_dominant_list().nth(0)   # First item in dominant group
        in_dominant_list().top(5)   # First 5 items
    """

    def nth(self, index: int) -> ElementQuery:
        """
        Select element at specific index in the dominant group.

        Args:
            index: 0-based index in the dominant group

        Returns:
            ElementQuery targeting the element at that position

        Example:
            in_dominant_list().nth(0)  # First item
            in_dominant_list().nth(2)  # Third item
        """
        query = ElementQuery()
        query._group_index = index
        query._from_dominant_list = True
        return query

    def top(self, n: int) -> MultiQuery:
        """
        Select the first n elements in the dominant group.

        Args:
            n: Number of elements to select

        Returns:
            MultiQuery representing the first n elements

        Example:
            in_dominant_list().top(5)  # First 5 items
        """
        return MultiQuery(limit=n, _parent_list_query=self)


def in_dominant_list() -> ListQuery:
    """
    Create a query over elements in the dominant group.

    The dominant group is the most common group_key in the snapshot,
    typically representing the main content list (search results,
    news feed items, product listings, etc.).

    Returns:
        ListQuery for chaining .nth(k) or .top(n)

    Example:
        in_dominant_list().nth(0)     # First item in dominant group
        in_dominant_list().top(5)     # First 5 items

        # With expect():
        expect(in_dominant_list().nth(0)).to_have_text_contains("Show HN")
    """
    return ListQuery()


# Export the factory as E for the Playwright-like API
# Users can do: from predicate.asserts import E
# And use: E(role="button"), E.submit(), E.link(text_contains="...")
