"""
Tests for verification module - assertion predicates for agent loops.
"""

import pytest

from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues
from sentience.verification import (
    AssertContext,
    AssertOutcome,
    all_of,
    any_of,
    custom,
    download_completed,
    element_count,
    exists,
    is_checked,
    is_collapsed,
    is_disabled,
    is_enabled,
    is_expanded,
    is_unchecked,
    not_exists,
    url_contains,
    url_matches,
    value_contains,
    value_equals,
)
from sentience.vision_executor import parse_vision_executor_action


def make_element(
    id: int,
    role: str = "button",
    text: str | None = None,
    importance: int = 100,
) -> Element:
    """Helper to create test elements."""
    return Element(
        id=id,
        role=role,
        text=text,
        importance=importance,
        bbox=BBox(x=0, y=0, width=100, height=50),
        visual_cues=VisualCues(is_primary=False, is_clickable=True, background_color_name=None),
    )


def make_snapshot(elements: list[Element], url: str = "https://example.com") -> Snapshot:
    """Helper to create test snapshots."""
    return Snapshot(
        status="success",
        url=url,
        elements=elements,
        viewport=Viewport(width=1920, height=1080),
    )


class TestUrlMatches:
    """Tests for url_matches predicate."""

    def test_matches_pattern(self):
        pred = url_matches(r"/search\?q=")
        ctx = AssertContext(url="https://example.com/search?q=shoes")
        outcome = pred(ctx)
        assert outcome.passed is True
        assert outcome.reason == ""

    def test_no_match(self):
        pred = url_matches(r"/cart")
        ctx = AssertContext(url="https://example.com/search?q=shoes")
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "did not match" in outcome.reason

    def test_none_url(self):
        pred = url_matches(r"/search")
        ctx = AssertContext(url=None)
        outcome = pred(ctx)
        assert outcome.passed is False

    def test_details_include_pattern_and_url(self):
        pred = url_matches(r"/test")
        ctx = AssertContext(url="https://example.com/test")
        outcome = pred(ctx)
        assert outcome.details["pattern"] == r"/test"
        assert "example.com" in outcome.details["url"]


class TestUrlContains:
    """Tests for url_contains predicate."""

    def test_contains_substring(self):
        pred = url_contains("/cart")
        ctx = AssertContext(url="https://example.com/cart/checkout")
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_no_substring(self):
        pred = url_contains("/orders")
        ctx = AssertContext(url="https://example.com/cart")
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "does not contain" in outcome.reason

    def test_none_url(self):
        pred = url_contains("/test")
        ctx = AssertContext(url=None)
        outcome = pred(ctx)
        assert outcome.passed is False


class TestExists:
    """Tests for exists predicate."""

    def test_element_exists(self):
        elements = [make_element(1, role="button", text="Click me")]
        snap = make_snapshot(elements)
        pred = exists("role=button")
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True
        assert outcome.details["matched"] == 1

    def test_element_not_found(self):
        elements = [make_element(1, role="button", text="Click me")]
        snap = make_snapshot(elements)
        pred = exists("role=link")
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "no elements matched" in outcome.reason

    def test_text_selector(self):
        elements = [make_element(1, role="button", text="Submit Form")]
        snap = make_snapshot(elements)
        pred = exists("text~'Submit'")
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_no_snapshot(self):
        pred = exists("role=button")
        ctx = AssertContext(snapshot=None)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "no snapshot available" in outcome.reason


class TestNotExists:
    """Tests for not_exists predicate."""

    def test_element_absent(self):
        elements = [make_element(1, role="button")]
        snap = make_snapshot(elements)
        pred = not_exists("text~'Loading'")
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_element_present(self):
        elements = [make_element(1, role="button", text="Loading...")]
        snap = make_snapshot(elements)
        pred = not_exists("text~'Loading'")
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "found 1 elements" in outcome.reason


class TestElementCount:
    """Tests for element_count predicate."""

    def test_min_count_satisfied(self):
        elements = [make_element(i, role="button") for i in range(3)]
        snap = make_snapshot(elements)
        pred = element_count("role=button", min_count=2)
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_min_count_not_satisfied(self):
        elements = [make_element(1, role="button")]
        snap = make_snapshot(elements)
        pred = element_count("role=button", min_count=5)
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "expected at least 5" in outcome.reason

    def test_max_count_satisfied(self):
        elements = [make_element(i, role="button") for i in range(3)]
        snap = make_snapshot(elements)
        pred = element_count("role=button", min_count=1, max_count=5)
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_max_count_exceeded(self):
        elements = [make_element(i, role="button") for i in range(10)]
        snap = make_snapshot(elements)
        pred = element_count("role=button", min_count=1, max_count=5)
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "expected 1-5" in outcome.reason


class TestAllOf:
    """Tests for all_of combinator."""

    def test_all_pass(self):
        elements = [make_element(1, role="button", text="Checkout")]
        snap = make_snapshot(elements, url="https://example.com/cart")
        pred = all_of(url_contains("/cart"), exists("role=button"))
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True
        assert outcome.details["failed_count"] == 0


class TestDownloadCompleted:
    def test_no_downloads(self):
        pred = download_completed()
        outcome = pred(AssertContext(downloads=[]))
        assert outcome.passed is False

    def test_completed_download_any(self):
        pred = download_completed()
        outcome = pred(
            AssertContext(
                downloads=[
                    {"status": "started", "suggested_filename": "a.txt"},
                    {"status": "completed", "suggested_filename": "report.pdf"},
                ]
            )
        )
        assert outcome.passed is True


def test_parse_vision_executor_action_click_xy():
    a = parse_vision_executor_action("CLICK_XY(10, 20)")
    assert a.kind == "click_xy"
    assert a.args["x"] == 10.0
    assert a.args["y"] == 20.0

    def test_completed_download_with_substring(self):
        pred = download_completed("report")
        outcome = pred(
            AssertContext(
                downloads=[
                    {"status": "completed", "suggested_filename": "report.pdf"},
                ]
            )
        )
        assert outcome.passed is True

    def test_one_fails(self):
        elements = [make_element(1, role="button")]
        snap = make_snapshot(elements, url="https://example.com/home")
        pred = all_of(url_contains("/cart"), exists("role=button"))
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert outcome.details["failed_count"] == 1

    def test_all_fail(self):
        elements = [make_element(1, role="link")]
        snap = make_snapshot(elements, url="https://example.com/home")
        pred = all_of(url_contains("/cart"), exists("role=button"))
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert outcome.details["failed_count"] == 2


class TestAnyOf:
    """Tests for any_of combinator."""

    def test_first_passes(self):
        elements = [make_element(1, role="button", text="Success")]
        snap = make_snapshot(elements)
        pred = any_of(exists("text~'Success'"), exists("text~'Complete'"))
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True


class TestStateAwarePredicates:
    def test_is_enabled_and_disabled(self):
        el1 = make_element(1, role="button", text="Submit")
        el2 = make_element(2, role="button", text="Disabled")
        el2 = el2.model_copy(update={"disabled": True})
        snap = make_snapshot([el1, el2])
        ctx = AssertContext(snapshot=snap, url=snap.url)

        assert is_enabled("role=button")(ctx).passed is True
        assert is_disabled("text~'Disabled'")(ctx).passed is True

    def test_checked_unchecked(self):
        el1 = make_element(1, role="checkbox", text="Opt in").model_copy(update={"checked": True})
        el2 = make_element(2, role="checkbox", text="Opt out").model_copy(update={"checked": False})
        snap = make_snapshot([el1, el2])
        ctx = AssertContext(snapshot=snap, url=snap.url)

        assert is_checked("text~'Opt in'")(ctx).passed is True
        assert is_unchecked("text~'Opt out'")(ctx).passed is True

    def test_value_equals_contains(self):
        el = make_element(1, role="textbox", text=None).model_copy(
            update={"value": "user@example.com"}
        )
        snap = make_snapshot([el])
        ctx = AssertContext(snapshot=snap, url=snap.url)

        assert value_equals("role=textbox", "user@example.com")(ctx).passed is True
        assert value_contains("role=textbox", "@example.com")(ctx).passed is True

    def test_expanded_collapsed(self):
        el1 = make_element(1, role="button", text="Menu").model_copy(update={"expanded": True})
        el2 = make_element(2, role="button", text="Details").model_copy(update={"expanded": False})
        snap = make_snapshot([el1, el2])
        ctx = AssertContext(snapshot=snap, url=snap.url)

        assert is_expanded("text~'Menu'")(ctx).passed is True
        assert is_collapsed("text~'Details'")(ctx).passed is True

    def test_second_passes(self):
        elements = [make_element(1, role="button", text="Complete")]
        snap = make_snapshot(elements)
        pred = any_of(exists("text~'Success'"), exists("text~'Complete'"))
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_none_pass(self):
        elements = [make_element(1, role="button", text="Error")]
        snap = make_snapshot(elements)
        pred = any_of(exists("text~'Success'"), exists("text~'Complete'"))
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "none of 2 predicates passed" in outcome.reason


class TestCustom:
    """Tests for custom predicate."""

    def test_custom_returns_true(self):
        pred = custom(lambda ctx: ctx.url is not None, "has_url")
        ctx = AssertContext(url="https://example.com")
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_custom_returns_false(self):
        pred = custom(lambda ctx: ctx.url is None, "no_url")
        ctx = AssertContext(url="https://example.com")
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "returned False" in outcome.reason

    def test_custom_with_snapshot(self):
        elements = [make_element(i, role="button") for i in range(15)]
        snap = make_snapshot(elements)
        pred = custom(
            lambda ctx: ctx.snapshot is not None and len(ctx.snapshot.elements) > 10,
            "has_many_elements",
        )
        ctx = AssertContext(snapshot=snap, url=snap.url)
        outcome = pred(ctx)
        assert outcome.passed is True

    def test_custom_exception(self):
        def bad_check(ctx):
            raise ValueError("Something went wrong")

        pred = custom(bad_check, "bad_check")
        ctx = AssertContext()
        outcome = pred(ctx)
        assert outcome.passed is False
        assert "raised exception" in outcome.reason
        assert "Something went wrong" in outcome.reason
