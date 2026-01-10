"""
Unit tests for ordinal intent detection and selection.

Tests the detect_ordinal_intent, select_by_ordinal, and boost_ordinal_elements functions.
"""

import pytest

from sentience.models import BBox, Element, VisualCues
from sentience.ordinal import (
    OrdinalIntent,
    boost_ordinal_elements,
    detect_ordinal_intent,
    select_by_ordinal,
)


class TestDetectOrdinalIntent:
    """Tests for detect_ordinal_intent function."""

    # Ordinal words
    def test_first(self):
        result = detect_ordinal_intent("Click the first result")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 1

    def test_second(self):
        result = detect_ordinal_intent("Select the second item")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 2

    def test_third(self):
        result = detect_ordinal_intent("Click the third option")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 3

    def test_fourth(self):
        result = detect_ordinal_intent("Choose the fourth link")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 4

    def test_fifth(self):
        result = detect_ordinal_intent("Click the fifth button")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 5

    def test_tenth(self):
        result = detect_ordinal_intent("Select the tenth item")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 10

    # Ordinal suffixes
    def test_1st(self):
        result = detect_ordinal_intent("Click the 1st result")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 1

    def test_2nd(self):
        result = detect_ordinal_intent("Select the 2nd item")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 2

    def test_3rd(self):
        result = detect_ordinal_intent("Click the 3rd option")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 3

    def test_4th(self):
        result = detect_ordinal_intent("Choose the 4th link")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 4

    def test_21st(self):
        result = detect_ordinal_intent("Select the 21st item")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 21

    def test_22nd(self):
        result = detect_ordinal_intent("Click the 22nd result")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 22

    def test_33rd(self):
        result = detect_ordinal_intent("Choose the 33rd option")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 33

    def test_100th(self):
        result = detect_ordinal_intent("Select the 100th item")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 100

    # Hash numbers
    def test_hash_1(self):
        result = detect_ordinal_intent("Click item #1")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 1

    def test_hash_3(self):
        result = detect_ordinal_intent("Select result #3")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 3

    def test_hash_10(self):
        result = detect_ordinal_intent("Choose option #10")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 10

    # Labeled numbers
    def test_item_number(self):
        result = detect_ordinal_intent("Click item 5")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 5

    def test_result_number(self):
        result = detect_ordinal_intent("Select result 3")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 3

    def test_option_number(self):
        result = detect_ordinal_intent("Choose option 2")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 2

    def test_number_word(self):
        result = detect_ordinal_intent("Click number 4")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 4

    def test_choice_number(self):
        result = detect_ordinal_intent("Select choice 1")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 1

    # Top/first keywords
    def test_top(self):
        result = detect_ordinal_intent("Click the top result")
        assert result.detected is True
        assert result.kind == "first"

    def test_top_case_insensitive(self):
        result = detect_ordinal_intent("Click the TOP result")
        assert result.detected is True
        assert result.kind == "first"

    # Top K
    def test_top_3(self):
        result = detect_ordinal_intent("Select the top 3 items")
        assert result.detected is True
        assert result.kind == "top_k"
        assert result.k == 3

    def test_top_5(self):
        result = detect_ordinal_intent("View top 5 results")
        assert result.detected is True
        assert result.kind == "top_k"
        assert result.k == 5

    def test_top_10(self):
        result = detect_ordinal_intent("Show top 10 products")
        assert result.detected is True
        assert result.kind == "top_k"
        assert result.k == 10

    # Last keywords
    def test_last(self):
        result = detect_ordinal_intent("Click the last item")
        assert result.detected is True
        assert result.kind == "last"

    def test_final(self):
        result = detect_ordinal_intent("Select the final option")
        assert result.detected is True
        assert result.kind == "last"

    def test_bottom(self):
        result = detect_ordinal_intent("Click the bottom result")
        assert result.detected is True
        assert result.kind == "last"

    # Next keywords
    def test_next(self):
        result = detect_ordinal_intent("Click the next button")
        assert result.detected is True
        assert result.kind == "next"

    def test_following(self):
        result = detect_ordinal_intent("Go to the following item")
        assert result.detected is True
        assert result.kind == "next"

    # Previous keywords
    def test_previous(self):
        result = detect_ordinal_intent("Click the previous button")
        assert result.detected is True
        assert result.kind == "previous"

    def test_preceding(self):
        result = detect_ordinal_intent("Go to the preceding item")
        assert result.detected is True
        assert result.kind == "previous"

    def test_prior(self):
        result = detect_ordinal_intent("Select the prior option")
        assert result.detected is True
        assert result.kind == "previous"

    # No ordinal intent
    def test_no_ordinal_click_button(self):
        result = detect_ordinal_intent("Click the submit button")
        assert result.detected is False
        assert result.kind is None

    def test_no_ordinal_search(self):
        result = detect_ordinal_intent("Search for laptops")
        assert result.detected is False

    def test_no_ordinal_type(self):
        result = detect_ordinal_intent("Type hello in the input")
        assert result.detected is False

    def test_empty_string(self):
        result = detect_ordinal_intent("")
        assert result.detected is False

    # Case insensitivity
    def test_case_insensitive_first(self):
        result = detect_ordinal_intent("Click the FIRST result")
        assert result.detected is True
        assert result.kind == "nth"
        assert result.n == 1

    def test_case_insensitive_last(self):
        result = detect_ordinal_intent("Select the LAST item")
        assert result.detected is True
        assert result.kind == "last"


def _make_element(
    id: int,
    text: str,
    group_key: str | None = None,
    group_index: int | None = None,
    importance: int = 100,
) -> Element:
    """Helper to create test elements."""
    return Element(
        id=id,
        role="button",
        text=text,
        importance=importance,
        bbox=BBox(x=0, y=id * 50, width=100, height=40),
        visual_cues=VisualCues(is_primary=False, background_color_name=None, is_clickable=True),
        in_viewport=True,
        is_occluded=False,
        z_index=0,
        group_key=group_key,
        group_index=group_index,
    )


class TestSelectByOrdinal:
    """Tests for select_by_ordinal function."""

    @pytest.fixture
    def elements(self) -> list[Element]:
        """Create a list of test elements in the dominant group."""
        return [
            _make_element(1, "Item A", "x100-w200-h40", 0),
            _make_element(2, "Item B", "x100-w200-h40", 1),
            _make_element(3, "Item C", "x100-w200-h40", 2),
            _make_element(4, "Item D", "x100-w200-h40", 3),
            _make_element(5, "Item E", "x100-w200-h40", 4),
            _make_element(6, "Other", "x500-w100-h30", 0),  # Different group
        ]

    def test_select_first(self, elements):
        intent = OrdinalIntent(detected=True, kind="first")
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert result is not None
        assert result.id == 1
        assert result.text == "Item A"

    def test_select_nth_2(self, elements):
        intent = OrdinalIntent(detected=True, kind="nth", n=2)
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert result is not None
        assert result.id == 2
        assert result.text == "Item B"

    def test_select_nth_5(self, elements):
        intent = OrdinalIntent(detected=True, kind="nth", n=5)
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert result is not None
        assert result.id == 5
        assert result.text == "Item E"

    def test_select_last(self, elements):
        intent = OrdinalIntent(detected=True, kind="last")
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert result is not None
        assert result.id == 5
        assert result.text == "Item E"

    def test_select_top_k(self, elements):
        intent = OrdinalIntent(detected=True, kind="top_k", k=3)
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert isinstance(result, list)
        assert len(result) == 3
        assert [e.id for e in result] == [1, 2, 3]

    def test_select_out_of_bounds(self, elements):
        intent = OrdinalIntent(detected=True, kind="nth", n=100)
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert result is None

    def test_select_no_dominant_group(self, elements):
        intent = OrdinalIntent(detected=True, kind="first")
        result = select_by_ordinal(elements, None, intent)
        # Should fall back to all elements sorted by group_index
        assert result is not None

    def test_select_not_detected(self, elements):
        intent = OrdinalIntent(detected=False)
        result = select_by_ordinal(elements, "x100-w200-h40", intent)
        assert result is None


class TestBoostOrdinalElements:
    """Tests for boost_ordinal_elements function."""

    @pytest.fixture
    def elements(self) -> list[Element]:
        """Create a list of test elements."""
        return [
            _make_element(1, "Item A", "x100-w200-h40", 0, importance=100),
            _make_element(2, "Item B", "x100-w200-h40", 1, importance=90),
            _make_element(3, "Item C", "x100-w200-h40", 2, importance=80),
            _make_element(4, "Item D", "x100-w200-h40", 3, importance=70),
            _make_element(5, "Other", "x500-w100-h30", 0, importance=200),
        ]

    def test_boost_first(self, elements):
        intent = OrdinalIntent(detected=True, kind="first")
        result = boost_ordinal_elements(elements, "x100-w200-h40", intent, boost_factor=10000)

        # First element should be boosted
        boosted = [e for e in result if e.id == 1][0]
        assert boosted.importance == 100 + 10000

        # Other elements unchanged
        other = [e for e in result if e.id == 2][0]
        assert other.importance == 90

    def test_boost_nth(self, elements):
        intent = OrdinalIntent(detected=True, kind="nth", n=3)
        result = boost_ordinal_elements(elements, "x100-w200-h40", intent, boost_factor=5000)

        # Third element should be boosted
        boosted = [e for e in result if e.id == 3][0]
        assert boosted.importance == 80 + 5000

    def test_boost_last(self, elements):
        intent = OrdinalIntent(detected=True, kind="last")
        result = boost_ordinal_elements(elements, "x100-w200-h40", intent, boost_factor=10000)

        # Last element in dominant group should be boosted (id=4, group_index=3)
        boosted = [e for e in result if e.id == 4][0]
        assert boosted.importance == 70 + 10000

    def test_boost_top_k(self, elements):
        intent = OrdinalIntent(detected=True, kind="top_k", k=2)
        result = boost_ordinal_elements(elements, "x100-w200-h40", intent, boost_factor=10000)

        # First two elements should be boosted
        first = [e for e in result if e.id == 1][0]
        second = [e for e in result if e.id == 2][0]
        third = [e for e in result if e.id == 3][0]

        assert first.importance == 100 + 10000
        assert second.importance == 90 + 10000
        assert third.importance == 80  # Not boosted

    def test_boost_not_detected(self, elements):
        intent = OrdinalIntent(detected=False)
        result = boost_ordinal_elements(elements, "x100-w200-h40", intent)

        # No elements should be boosted
        for orig, boosted in zip(elements, result):
            assert orig.importance == boosted.importance

    def test_boost_returns_copy(self, elements):
        intent = OrdinalIntent(detected=True, kind="first")
        result = boost_ordinal_elements(elements, "x100-w200-h40", intent)

        # Original elements should not be modified
        assert elements[0].importance == 100


class TestOrdinalIntent:
    """Tests for OrdinalIntent dataclass."""

    def test_default_values(self):
        intent = OrdinalIntent(detected=False)
        assert intent.detected is False
        assert intent.kind is None
        assert intent.n is None
        assert intent.k is None

    def test_with_nth(self):
        intent = OrdinalIntent(detected=True, kind="nth", n=5)
        assert intent.detected is True
        assert intent.kind == "nth"
        assert intent.n == 5

    def test_with_top_k(self):
        intent = OrdinalIntent(detected=True, kind="top_k", k=3)
        assert intent.detected is True
        assert intent.kind == "top_k"
        assert intent.k == 3
