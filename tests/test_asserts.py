"""
Tests for assertion DSL module (predicate.asserts).

Tests the E() query builder, expect() fluent API, and in_dominant_list() operations.
"""

import pytest

from predicate.asserts import (
    E,
    ElementQuery,
    EventuallyConfig,
    EventuallyWrapper,
    ListQuery,
    MultiQuery,
    expect,
    in_dominant_list,
    with_eventually,
)
from predicate.models import BBox, Element, Snapshot, Viewport, VisualCues
from predicate.verification import AssertContext


def make_element(
    id: int,
    role: str = "button",
    text: str | None = None,
    importance: int = 100,
    in_viewport: bool = True,
    is_occluded: bool = False,
    group_key: str | None = None,
    group_index: int | None = None,
    href: str | None = None,
    doc_y: float | None = None,
) -> Element:
    """Helper to create test elements."""
    return Element(
        id=id,
        role=role,
        text=text,
        importance=importance,
        bbox=BBox(x=0, y=doc_y or 0, width=100, height=50),
        visual_cues=VisualCues(is_primary=False, is_clickable=True, background_color_name=None),
        in_viewport=in_viewport,
        is_occluded=is_occluded,
        group_key=group_key,
        group_index=group_index,
        href=href,
        doc_y=doc_y,
    )


def make_snapshot(
    elements: list[Element],
    url: str = "https://example.com",
    dominant_group_key: str | None = None,
) -> Snapshot:
    """Helper to create test snapshots."""
    return Snapshot(
        status="success",
        url=url,
        elements=elements,
        viewport=Viewport(width=1920, height=1080),
        dominant_group_key=dominant_group_key,
    )


class TestElementQuery:
    """Tests for E() query builder."""

    def test_create_basic_query(self):
        """E() creates ElementQuery with specified fields."""
        q = E(role="button", text_contains="Save")
        assert q.role == "button"
        assert q.text_contains == "Save"
        assert q.name is None
        assert q.in_viewport is None

    def test_create_with_all_fields(self):
        """E() accepts all documented fields."""
        q = E(
            role="link",
            name="Home",
            text="Home Page",
            text_contains="Home",
            href_contains="/home",
            in_viewport=True,
            occluded=False,
            group="nav",
            in_dominant_group=True,
        )
        assert q.role == "link"
        assert q.name == "Home"
        assert q.text == "Home Page"
        assert q.text_contains == "Home"
        assert q.href_contains == "/home"
        assert q.in_viewport is True
        assert q.occluded is False
        assert q.group == "nav"
        assert q.in_dominant_group is True

    def test_matches_role(self):
        """ElementQuery.matches() filters by role."""
        el = make_element(1, role="button", text="Click")
        q = E(role="button")
        assert q.matches(el) is True

        q2 = E(role="link")
        assert q2.matches(el) is False

    def test_matches_text_exact(self):
        """ElementQuery.matches() filters by exact text."""
        el = make_element(1, text="Save")
        q = E(text="Save")
        assert q.matches(el) is True

        q2 = E(text="Save Changes")
        assert q2.matches(el) is False

    def test_matches_text_contains(self):
        """ElementQuery.matches() filters by text substring (case-insensitive)."""
        el = make_element(1, text="Save Changes Now")
        q = E(text_contains="changes")
        assert q.matches(el) is True

        q2 = E(text_contains="delete")
        assert q2.matches(el) is False

    def test_matches_href_contains(self):
        """ElementQuery.matches() filters by href substring."""
        el = make_element(1, role="link", href="https://example.com/cart/checkout")
        q = E(href_contains="/cart")
        assert q.matches(el) is True

        q2 = E(href_contains="/orders")
        assert q2.matches(el) is False

    def test_matches_in_viewport(self):
        """ElementQuery.matches() filters by viewport visibility."""
        el_visible = make_element(1, in_viewport=True)
        el_hidden = make_element(2, in_viewport=False)

        q = E(in_viewport=True)
        assert q.matches(el_visible) is True
        assert q.matches(el_hidden) is False

    def test_matches_occluded(self):
        """ElementQuery.matches() filters by occlusion state."""
        el_clear = make_element(1, is_occluded=False)
        el_occluded = make_element(2, is_occluded=True)

        q = E(occluded=False)
        assert q.matches(el_clear) is True
        assert q.matches(el_occluded) is False

    def test_matches_group_key(self):
        """ElementQuery.matches() filters by exact group_key."""
        el = make_element(1, group_key="main-list")
        q = E(group="main-list")
        assert q.matches(el) is True

        q2 = E(group="sidebar")
        assert q2.matches(el) is False

    def test_matches_in_dominant_group(self):
        """ElementQuery.matches() filters by dominant group membership."""
        el_in_dg = make_element(1, group_key="main-list")
        el_not_in_dg = make_element(2, group_key="sidebar")
        snap = make_snapshot([el_in_dg, el_not_in_dg], dominant_group_key="main-list")

        q = E(in_dominant_group=True)
        assert q.matches(el_in_dg, snap) is True
        assert q.matches(el_not_in_dg, snap) is False

    def test_find_all_returns_matching(self):
        """ElementQuery.find_all() returns all matching elements."""
        elements = [
            make_element(1, role="button", text="Save"),
            make_element(2, role="button", text="Cancel"),
            make_element(3, role="link", text="Help"),
        ]
        snap = make_snapshot(elements)

        q = E(role="button")
        matches = q.find_all(snap)
        assert len(matches) == 2
        assert all(el.role == "button" for el in matches)

    def test_find_first_returns_first_match(self):
        """ElementQuery.find_first() returns first matching element."""
        elements = [
            make_element(1, role="button", text="First", doc_y=100),
            make_element(2, role="button", text="Second", doc_y=200),
        ]
        snap = make_snapshot(elements)

        q = E(role="button")
        match = q.find_first(snap)
        assert match is not None
        assert match.text == "First"

    def test_find_first_returns_none_when_no_match(self):
        """ElementQuery.find_first() returns None when no match."""
        elements = [make_element(1, role="button")]
        snap = make_snapshot(elements)

        q = E(role="link")
        match = q.find_first(snap)
        assert match is None


class TestListQuery:
    """Tests for in_dominant_list() and ListQuery."""

    def test_in_dominant_list_returns_list_query(self):
        """in_dominant_list() returns ListQuery."""
        lq = in_dominant_list()
        assert isinstance(lq, ListQuery)

    def test_nth_returns_element_query(self):
        """ListQuery.nth() returns ElementQuery with group_index set."""
        lq = in_dominant_list()
        eq = lq.nth(2)
        assert isinstance(eq, ElementQuery)
        assert eq._group_index == 2
        assert eq._from_dominant_list is True

    def test_top_returns_multi_query(self):
        """ListQuery.top() returns MultiQuery."""
        lq = in_dominant_list()
        mq = lq.top(5)
        assert isinstance(mq, MultiQuery)
        assert mq.limit == 5

    def test_nth_matches_by_group_index(self):
        """ElementQuery from .nth() matches elements by group_index."""
        elements = [
            make_element(1, text="First", group_key="main", group_index=0),
            make_element(2, text="Second", group_key="main", group_index=1),
            make_element(3, text="Third", group_key="main", group_index=2),
        ]
        snap = make_snapshot(elements, dominant_group_key="main")

        # .nth(1) should match element with group_index=1
        q = in_dominant_list().nth(1)
        matches = q.find_all(snap)
        assert len(matches) == 1
        assert matches[0].text == "Second"

    def test_nth_only_matches_dominant_group(self):
        """ElementQuery from .nth() only matches elements in dominant group."""
        elements = [
            make_element(1, text="Main Item", group_key="main", group_index=0),
            make_element(2, text="Side Item", group_key="sidebar", group_index=0),
        ]
        snap = make_snapshot(elements, dominant_group_key="main")

        q = in_dominant_list().nth(0)
        matches = q.find_all(snap)
        assert len(matches) == 1
        assert matches[0].text == "Main Item"


class TestExpectBuilder:
    """Tests for expect() builder and matchers."""

    def test_to_exist_passes_when_element_found(self):
        """expect(...).to_exist() passes when element matches."""
        elements = [make_element(1, role="button", text="Save")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(role="button")).to_exist()
        outcome = pred(ctx)
        assert outcome.passed is True
        assert outcome.details["matched"] == 1

    def test_to_exist_fails_when_element_not_found(self):
        """expect(...).to_exist() fails when no element matches."""
        elements = [make_element(1, role="button")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(role="link")).to_exist()
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "no elements matched" in outcome.reason

    def test_to_exist_fails_without_snapshot(self):
        """expect(...).to_exist() fails when no snapshot available."""
        ctx = AssertContext(snapshot=None)

        pred = expect(E(role="button")).to_exist()
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "no snapshot available" in outcome.reason

    def test_not_to_exist_passes_when_element_absent(self):
        """expect(...).not_to_exist() passes when no element matches."""
        elements = [make_element(1, role="button")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(role="link")).not_to_exist()
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_not_to_exist_fails_when_element_found(self):
        """expect(...).not_to_exist() fails when element matches."""
        elements = [make_element(1, role="button", text="Error")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(text_contains="Error")).not_to_exist()
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "found 1 elements" in outcome.reason

    def test_to_be_visible_passes_when_visible(self):
        """expect(...).to_be_visible() passes when element is in_viewport and not occluded."""
        elements = [make_element(1, role="button", in_viewport=True, is_occluded=False)]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(role="button")).to_be_visible()
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_to_be_visible_fails_when_out_of_viewport(self):
        """expect(...).to_be_visible() fails when element is not in viewport."""
        elements = [make_element(1, role="button", in_viewport=False, is_occluded=False)]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(role="button")).to_be_visible()
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "not visible" in outcome.reason

    def test_to_be_visible_fails_when_occluded(self):
        """expect(...).to_be_visible() fails when element is occluded."""
        elements = [make_element(1, role="button", in_viewport=True, is_occluded=True)]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E(role="button")).to_be_visible()
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "not visible" in outcome.reason

    def test_to_have_text_contains_passes(self):
        """expect(...).to_have_text_contains() passes when text matches."""
        elements = [make_element(1, text="Welcome to our site")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E()).to_have_text_contains("Welcome")
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_to_have_text_contains_fails(self):
        """expect(...).to_have_text_contains() fails when text doesn't match."""
        elements = [make_element(1, text="Hello World")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect(E()).to_have_text_contains("Goodbye")
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "does not contain" in outcome.reason


class TestExpectGlobalAssertions:
    """Tests for expect.text_present() and expect.no_text()."""

    def test_text_present_passes_when_found(self):
        """expect.text_present() passes when text found anywhere on page."""
        elements = [
            make_element(1, text="Header"),
            make_element(2, text="Welcome back, user!"),
            make_element(3, text="Footer"),
        ]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect.text_present("Welcome back")
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_text_present_fails_when_not_found(self):
        """expect.text_present() fails when text not found."""
        elements = [make_element(1, text="Hello World")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect.text_present("Goodbye")
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "not found on page" in outcome.reason

    def test_text_present_case_insensitive(self):
        """expect.text_present() is case-insensitive."""
        elements = [make_element(1, text="WELCOME")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect.text_present("welcome")
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_no_text_passes_when_absent(self):
        """expect.no_text() passes when text not found."""
        elements = [make_element(1, text="Success")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect.no_text("Error")
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_no_text_fails_when_found(self):
        """expect.no_text() fails when text found."""
        elements = [make_element(1, text="Error: Something went wrong")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        pred = expect.no_text("Error")
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "text 'Error' found" in outcome.reason


class TestWithEventually:
    """Tests for with_eventually() wrapper."""

    def test_config_defaults(self):
        """EventuallyConfig has correct defaults."""
        config = EventuallyConfig()
        assert config.timeout == 10
        assert config.poll == 0.2
        assert config.max_retries == 3

    def test_with_eventually_creates_wrapper(self):
        """with_eventually() creates EventuallyWrapper."""
        pred = expect(E(role="button")).to_exist()
        wrapper = with_eventually(pred, timeout=5, max_retries=2)
        assert isinstance(wrapper, EventuallyWrapper)

    def test_with_eventually_custom_config(self):
        """with_eventually() accepts custom config values."""
        pred = expect(E(role="button")).to_exist()
        wrapper = with_eventually(pred, timeout=30, poll=1.0, max_retries=10)
        assert wrapper._config.timeout == 30
        assert wrapper._config.poll == 1.0
        assert wrapper._config.max_retries == 10


class TestDominantListOrdinalAssertions:
    """Tests for ordinal assertions on dominant group."""

    def test_nth_with_to_have_text_contains(self):
        """in_dominant_list().nth(k).to_have_text_contains() works."""
        elements = [
            make_element(1, text="Show HN: Cool Project", group_key="feed", group_index=0),
            make_element(2, text="Ask HN: Best IDE?", group_key="feed", group_index=1),
            make_element(3, text="Regular news story", group_key="feed", group_index=2),
        ]
        snap = make_snapshot(elements, dominant_group_key="feed")
        ctx = AssertContext(snapshot=snap, url=snap.url)

        # First item should contain "Show HN"
        pred = expect(in_dominant_list().nth(0)).to_have_text_contains("Show HN")
        outcome = pred(ctx)
        assert outcome.passed is True

        # Second item should contain "Ask HN"
        pred2 = expect(in_dominant_list().nth(1)).to_have_text_contains("Ask HN")
        outcome2 = pred2(ctx)
        assert outcome2.passed is True

        # First item should NOT contain "Ask HN"
        pred3 = expect(in_dominant_list().nth(0)).to_have_text_contains("Ask HN")
        outcome3 = pred3(ctx)
        assert outcome3.passed is False


class TestIntegrationWithAgentRuntime:
    """Tests verifying DSL integrates with AgentRuntime.assert_()."""

    def test_predicate_callable_with_context(self):
        """DSL predicates are callable with AssertContext."""
        elements = [make_element(1, role="button", text="Submit")]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        # All these should be valid predicates
        preds = [
            expect(E(role="button")).to_exist(),
            expect(E(role="link")).not_to_exist(),
            expect(E(role="button")).to_be_visible(),
            expect(E()).to_have_text_contains("Submit"),
            expect.text_present("Submit"),
            expect.no_text("Error"),
        ]

        for pred in preds:
            # Should be callable
            assert callable(pred)
            # Should return AssertOutcome when called with context
            outcome = pred(ctx)
            assert hasattr(outcome, "passed")
            assert hasattr(outcome, "reason")
            assert hasattr(outcome, "details")

    def test_complex_query_combinations(self):
        """Complex queries work correctly."""
        elements = [
            make_element(1, role="button", text="Save", in_viewport=True, is_occluded=False),
            make_element(2, role="button", text="Cancel", in_viewport=True, is_occluded=True),
            make_element(3, role="link", text="Help", href="/help", in_viewport=False),
        ]
        snap = make_snapshot(elements)
        ctx = AssertContext(snapshot=snap, url=snap.url)

        # Visible button with text "Save"
        pred = expect(
            E(role="button", text_contains="Save", in_viewport=True, occluded=False)
        ).to_exist()
        assert pred(ctx).passed is True

        # Visible button with text "Cancel" - fails because it's occluded
        pred2 = expect(E(role="button", text_contains="Cancel", occluded=False)).to_exist()
        assert pred2(ctx).passed is False

        # Link to help page
        pred3 = expect(E(role="link", href_contains="/help")).to_exist()
        assert pred3(ctx).passed is True
