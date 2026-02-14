"""
Expectation builder for assertion DSL.

This module provides the expect() builder that creates fluent assertions
which compile to existing Predicate objects.

Key classes:
- ExpectBuilder: Fluent builder for element-based assertions
- EventuallyBuilder: Wrapper for retry logic (.eventually())

The expect() function is the main entry point. It returns a builder that
can be chained with matchers:
    expect(E(role="button")).to_exist()
    expect(E(text_contains="Error")).not_to_exist()
    expect.text_present("Welcome")

All builders compile to Predicate functions compatible with AgentRuntime.assert_().
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..verification import AssertContext, AssertOutcome, Predicate
from .query import ElementQuery, ListQuery, MultiQuery, _MultiTextPredicate

if TYPE_CHECKING:
    from ..models import Snapshot


# Default values for .eventually()
DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_POLL = 0.2  # seconds
DEFAULT_MAX_RETRIES = 3


@dataclass
class EventuallyConfig:
    """Configuration for .eventually() retry logic."""

    timeout: float = DEFAULT_TIMEOUT  # Max time to wait (seconds)
    poll: float = DEFAULT_POLL  # Interval between retries (seconds)
    max_retries: int = DEFAULT_MAX_RETRIES  # Max number of retry attempts
    # Optional: increase SnapshotOptions.limit across retries (additive schedule).
    # See docs/expand_deterministic_verifications_sdk.md for details.
    snapshot_limit_growth: dict[str, Any] | None = None


class ExpectBuilder:
    """
    Fluent builder for element-based assertions.

    Created by expect(E(...)) or expect(in_dominant_list().nth(k)).

    Methods return Predicate functions that can be passed to runtime.assert_().

    Example:
        expect(E(role="button")).to_exist()
        expect(E(text_contains="Error")).not_to_exist()
        expect(E(role="link")).to_be_visible()
    """

    def __init__(self, query: ElementQuery | MultiQuery | _MultiTextPredicate):
        """
        Initialize builder with query.

        Args:
            query: ElementQuery, MultiQuery, or _MultiTextPredicate
        """
        self._query = query

    def to_exist(self) -> Predicate:
        """
        Assert that at least one element matches the query.

        Returns:
            Predicate function for use with runtime.assert_()

        Example:
            runtime.assert_(
                expect(E(role="button", text_contains="Save")).to_exist(),
                label="save_button_exists"
            )
        """
        query = self._query

        def _pred(ctx: AssertContext) -> AssertOutcome:
            snap = ctx.snapshot
            if snap is None:
                return AssertOutcome(
                    passed=False,
                    reason="no snapshot available",
                    details={"query": _query_to_dict(query)},
                )

            if isinstance(query, ElementQuery):
                matches = query.find_all(snap)
                ok = len(matches) > 0
                return AssertOutcome(
                    passed=ok,
                    reason="" if ok else f"no elements matched query: {_query_to_dict(query)}",
                    details={"query": _query_to_dict(query), "matched": len(matches)},
                )
            else:
                return AssertOutcome(
                    passed=False,
                    reason="to_exist() requires ElementQuery",
                    details={},
                )

        return _pred

    def not_to_exist(self) -> Predicate:
        """
        Assert that NO elements match the query.

        Useful for asserting absence of error messages, loading indicators, etc.

        Returns:
            Predicate function for use with runtime.assert_()

        Example:
            runtime.assert_(
                expect(E(text_contains="Error")).not_to_exist(),
                label="no_error_message"
            )
        """
        query = self._query

        def _pred(ctx: AssertContext) -> AssertOutcome:
            snap = ctx.snapshot
            if snap is None:
                return AssertOutcome(
                    passed=False,
                    reason="no snapshot available",
                    details={"query": _query_to_dict(query)},
                )

            if isinstance(query, ElementQuery):
                matches = query.find_all(snap)
                ok = len(matches) == 0
                return AssertOutcome(
                    passed=ok,
                    reason=(
                        ""
                        if ok
                        else f"found {len(matches)} elements matching: {_query_to_dict(query)}"
                    ),
                    details={"query": _query_to_dict(query), "matched": len(matches)},
                )
            else:
                return AssertOutcome(
                    passed=False,
                    reason="not_to_exist() requires ElementQuery",
                    details={},
                )

        return _pred

    def to_be_visible(self) -> Predicate:
        """
        Assert that element exists AND is visible (in_viewport=True, occluded=False).

        Returns:
            Predicate function for use with runtime.assert_()

        Example:
            runtime.assert_(
                expect(E(text_contains="Checkout")).to_be_visible(),
                label="checkout_button_visible"
            )
        """
        query = self._query

        def _pred(ctx: AssertContext) -> AssertOutcome:
            snap = ctx.snapshot
            if snap is None:
                return AssertOutcome(
                    passed=False,
                    reason="no snapshot available",
                    details={"query": _query_to_dict(query)},
                )

            if isinstance(query, ElementQuery):
                matches = query.find_all(snap)
                if len(matches) == 0:
                    return AssertOutcome(
                        passed=False,
                        reason=f"no elements matched query: {_query_to_dict(query)}",
                        details={"query": _query_to_dict(query), "matched": 0},
                    )

                # Check visibility of first match
                el = matches[0]
                is_visible = el.in_viewport and not el.is_occluded
                return AssertOutcome(
                    passed=is_visible,
                    reason=(
                        ""
                        if is_visible
                        else f"element found but not visible (in_viewport={el.in_viewport}, is_occluded={el.is_occluded})"
                    ),
                    details={
                        "query": _query_to_dict(query),
                        "element_id": el.id,
                        "in_viewport": el.in_viewport,
                        "is_occluded": el.is_occluded,
                    },
                )
            else:
                return AssertOutcome(
                    passed=False,
                    reason="to_be_visible() requires ElementQuery",
                    details={},
                )

        return _pred

    def to_have_text_contains(self, text: str) -> Predicate:
        """
        Assert that element's text contains the specified substring.

        Args:
            text: Substring to search for (case-insensitive)

        Returns:
            Predicate function for use with runtime.assert_()

        Example:
            runtime.assert_(
                expect(in_dominant_list().nth(0)).to_have_text_contains("Show HN"),
                label="first_item_is_show_hn"
            )
        """
        query = self._query

        def _pred(ctx: AssertContext) -> AssertOutcome:
            snap = ctx.snapshot
            if snap is None:
                return AssertOutcome(
                    passed=False,
                    reason="no snapshot available",
                    details={"query": _query_to_dict(query), "expected_text": text},
                )

            if isinstance(query, ElementQuery):
                matches = query.find_all(snap)
                if len(matches) == 0:
                    return AssertOutcome(
                        passed=False,
                        reason=f"no elements matched query: {_query_to_dict(query)}",
                        details={
                            "query": _query_to_dict(query),
                            "matched": 0,
                            "expected_text": text,
                        },
                    )

                # Check text of first match
                el = matches[0]
                el_text = el.text or ""
                ok = text.lower() in el_text.lower()
                return AssertOutcome(
                    passed=ok,
                    reason=(
                        "" if ok else f"element text '{el_text[:100]}' does not contain '{text}'"
                    ),
                    details={
                        "query": _query_to_dict(query),
                        "element_id": el.id,
                        "element_text": el_text[:200],
                        "expected_text": text,
                    },
                )
            elif isinstance(query, _MultiTextPredicate):
                # This is from MultiQuery.any_text_contains()
                # Already handled by that method
                return AssertOutcome(
                    passed=False,
                    reason="use any_text_contains() for MultiQuery",
                    details={},
                )
            else:
                return AssertOutcome(
                    passed=False,
                    reason="to_have_text_contains() requires ElementQuery",
                    details={},
                )

        return _pred


class _ExpectFactory:
    """
    Factory for creating ExpectBuilder instances and global assertions.

    This is the main entry point for the assertion DSL.

    Usage:
        from predicate.asserts import expect, E

        # Element-based assertions
        expect(E(role="button")).to_exist()
        expect(E(text_contains="Error")).not_to_exist()

        # Global text assertions
        expect.text_present("Welcome back")
        expect.no_text("Error")
    """

    def __call__(
        self,
        query: ElementQuery | ListQuery | MultiQuery | _MultiTextPredicate,
    ) -> ExpectBuilder:
        """
        Create an expectation builder for the given query.

        Args:
            query: ElementQuery, ListQuery.nth() result, MultiQuery, or _MultiTextPredicate

        Returns:
            ExpectBuilder for chaining matchers

        Example:
            expect(E(role="button")).to_exist()
            expect(in_dominant_list().nth(0)).to_have_text_contains("Show HN")
        """
        if isinstance(query, (ElementQuery, MultiQuery, _MultiTextPredicate)):
            return ExpectBuilder(query)
        else:
            raise TypeError(
                f"expect() requires ElementQuery, MultiQuery, or _MultiTextPredicate, got {type(query)}"
            )

    def text_present(self, text: str) -> Predicate:
        """
        Global assertion: check if text is present anywhere on the page.

        Searches across all element text_norm fields.

        Args:
            text: Text to search for (case-insensitive substring)

        Returns:
            Predicate function for use with runtime.assert_()

        Example:
            runtime.assert_(
                expect.text_present("Welcome back"),
                label="user_logged_in"
            )
        """

        def _pred(ctx: AssertContext) -> AssertOutcome:
            snap = ctx.snapshot
            if snap is None:
                return AssertOutcome(
                    passed=False,
                    reason="no snapshot available",
                    details={"search_text": text},
                )

            # Search all element texts
            text_lower = text.lower()
            for el in snap.elements:
                el_text = el.text or ""
                if text_lower in el_text.lower():
                    return AssertOutcome(
                        passed=True,
                        reason="",
                        details={"search_text": text, "found_in_element": el.id},
                    )

            return AssertOutcome(
                passed=False,
                reason=f"text '{text}' not found on page",
                details={"search_text": text, "elements_searched": len(snap.elements)},
            )

        return _pred

    def no_text(self, text: str) -> Predicate:
        """
        Global assertion: check that text is NOT present anywhere on the page.

        Searches across all element text_norm fields.

        Args:
            text: Text that should not be present (case-insensitive substring)

        Returns:
            Predicate function for use with runtime.assert_()

        Example:
            runtime.assert_(
                expect.no_text("Error"),
                label="no_error_message"
            )
        """

        def _pred(ctx: AssertContext) -> AssertOutcome:
            snap = ctx.snapshot
            if snap is None:
                return AssertOutcome(
                    passed=False,
                    reason="no snapshot available",
                    details={"search_text": text},
                )

            # Search all element texts
            text_lower = text.lower()
            for el in snap.elements:
                el_text = el.text or ""
                if text_lower in el_text.lower():
                    return AssertOutcome(
                        passed=False,
                        reason=f"text '{text}' found in element id={el.id}",
                        details={
                            "search_text": text,
                            "found_in_element": el.id,
                            "element_text": el_text[:200],
                        },
                    )

            return AssertOutcome(
                passed=True,
                reason="",
                details={"search_text": text, "elements_searched": len(snap.elements)},
            )

        return _pred


# Create the singleton factory
expect = _ExpectFactory()


def _query_to_dict(query: ElementQuery | MultiQuery | _MultiTextPredicate | Any) -> dict[str, Any]:
    """Convert query to a serializable dict for debugging."""
    if isinstance(query, ElementQuery):
        result = {}
        if query.role:
            result["role"] = query.role
        if query.name:
            result["name"] = query.name
        if query.text:
            result["text"] = query.text
        if query.text_contains:
            result["text_contains"] = query.text_contains
        if query.href_contains:
            result["href_contains"] = query.href_contains
        if query.in_viewport is not None:
            result["in_viewport"] = query.in_viewport
        if query.occluded is not None:
            result["occluded"] = query.occluded
        if query.group:
            result["group"] = query.group
        if query.in_dominant_group is not None:
            result["in_dominant_group"] = query.in_dominant_group
        if query._group_index is not None:
            result["group_index"] = query._group_index
        if query._from_dominant_list:
            result["from_dominant_list"] = True
        return result
    elif isinstance(query, MultiQuery):
        return {"type": "multi", "limit": query.limit}
    elif isinstance(query, _MultiTextPredicate):
        return {
            "type": "multi_text",
            "text": query.text,
            "check_type": query.check_type,
        }
    else:
        return {"type": str(type(query))}


class EventuallyWrapper:
    """
    Wrapper that adds retry logic to a predicate.

    Created by calling .eventually() on an ExpectBuilder method result.
    This is a helper that executes retries by taking fresh snapshots.

    Note: .eventually() returns an async function that must be awaited.
    """

    def __init__(
        self,
        predicate: Predicate,
        config: EventuallyConfig,
    ):
        """
        Initialize eventually wrapper.

        Args:
            predicate: The predicate to retry
            config: Retry configuration
        """
        self._predicate = predicate
        self._config = config

    async def evaluate(self, ctx: AssertContext, snapshot_fn) -> AssertOutcome:
        """
        Evaluate predicate with retry logic.

        Args:
            ctx: Initial assertion context
            snapshot_fn: Async function to take fresh snapshots

        Returns:
            AssertOutcome from successful evaluation or last failed attempt
        """
        start_time = time.monotonic()
        last_outcome: AssertOutcome | None = None
        attempts = 0

        growth = self._config.snapshot_limit_growth
        growth_apply_on = "only_on_fail"
        growth_start: int | None = None
        growth_step: int | None = None
        growth_max: int | None = None
        if isinstance(growth, dict) and growth:
            try:
                growth_apply_on = str(growth.get("apply_on") or "only_on_fail")
            except Exception:
                growth_apply_on = "only_on_fail"
            try:
                v = growth.get("start_limit", None)
                growth_start = int(v) if v is not None else None
            except Exception:
                growth_start = None
            try:
                v = growth.get("step", None)
                growth_step = int(v) if v is not None else None
            except Exception:
                growth_step = None
            try:
                v = growth.get("max_limit", None)
                growth_max = int(v) if v is not None else None
            except Exception:
                growth_max = None

        if growth and growth_start is None:
            growth_start = 50
        if growth and growth_step is None:
            growth_step = max(1, int(growth_start or 50))
        if growth and growth_max is None:
            growth_max = 500

        def _clamp_limit(n: int) -> int:
            if n < 1:
                return 1
            if n > 500:
                return 500
            return n

        def _limit_for_attempt(attempt_idx_1based: int) -> int:
            assert growth_start is not None and growth_step is not None and growth_max is not None
            base = int(growth_start) + int(growth_step) * max(0, int(attempt_idx_1based) - 1)
            return _clamp_limit(min(int(growth_max), base))

        while True:
            # Check timeout (higher precedence than max_retries)
            elapsed = time.monotonic() - start_time
            if elapsed >= self._config.timeout:
                if last_outcome:
                    last_outcome.reason = f"timeout after {elapsed:.1f}s: {last_outcome.reason}"
                    return last_outcome
                return AssertOutcome(
                    passed=False,
                    reason=f"timeout after {elapsed:.1f}s",
                    details={"attempts": attempts},
                )

            # Check max retries
            if attempts >= self._config.max_retries:
                if last_outcome:
                    last_outcome.reason = (
                        f"max retries ({self._config.max_retries}) exceeded: {last_outcome.reason}"
                    )
                    return last_outcome
                return AssertOutcome(
                    passed=False,
                    reason=f"max retries ({self._config.max_retries}) exceeded",
                    details={"attempts": attempts},
                )

            # Take fresh snapshot if not first attempt
            if attempts > 0:
                try:
                    # If snapshot_fn supports kwargs (e.g. runtime.snapshot), pass adaptive limit.
                    snap_limit = None
                    if growth:
                        # attempts is 1-based for the snapshot attempt here (attempts>0 means >=2nd try)
                        attempt_idx = attempts + 1
                        apply = growth_apply_on == "all" or (
                            growth_apply_on == "only_on_fail" and last_outcome is not None
                        )
                        if apply:
                            snap_limit = _limit_for_attempt(attempt_idx)
                    if snap_limit is not None:
                        try:
                            fresh_snapshot = await snapshot_fn(limit=int(snap_limit))
                        except TypeError:
                            fresh_snapshot = await snapshot_fn()
                    else:
                        fresh_snapshot = await snapshot_fn()
                    ctx = AssertContext(
                        snapshot=fresh_snapshot,
                        url=fresh_snapshot.url if fresh_snapshot else ctx.url,
                        step_id=ctx.step_id,
                    )
                except Exception as e:
                    last_outcome = AssertOutcome(
                        passed=False,
                        reason=f"failed to take snapshot: {e}",
                        details={"attempts": attempts, "error": str(e)},
                    )
                    attempts += 1
                    await asyncio.sleep(self._config.poll)
                    continue

            # Evaluate predicate
            outcome = self._predicate(ctx)
            if outcome.passed:
                outcome.details["attempts"] = attempts + 1
                return outcome

            last_outcome = outcome
            attempts += 1

            # Wait before next retry
            if attempts < self._config.max_retries:
                # Check if we'd exceed timeout with the poll delay
                if (time.monotonic() - start_time + self._config.poll) < self._config.timeout:
                    await asyncio.sleep(self._config.poll)
                else:
                    # No point waiting, we'll timeout anyway
                    last_outcome.reason = (
                        f"timeout after {time.monotonic() - start_time:.1f}s: {last_outcome.reason}"
                    )
                    return last_outcome

        return last_outcome or AssertOutcome(passed=False, reason="unexpected state")


def with_eventually(
    predicate: Predicate,
    timeout: float = DEFAULT_TIMEOUT,
    poll: float = DEFAULT_POLL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    snapshot_limit_growth: dict[str, Any] | None = None,
) -> EventuallyWrapper:
    """
    Wrap a predicate with retry logic.

    This is the Python API for .eventually(). Since Python predicates
    are synchronous, this returns a wrapper that provides an async
    evaluate() method for use with the runtime.

    Args:
        predicate: Predicate to wrap
        timeout: Max time to wait (seconds, default 10)
        poll: Interval between retries (seconds, default 0.2)
        max_retries: Max number of retry attempts (default 3)

    Returns:
        EventuallyWrapper with async evaluate() method

    Example:
        wrapper = with_eventually(
            expect(E(role="button")).to_exist(),
            timeout=5,
            max_retries=10
        )
        result = await wrapper.evaluate(ctx, runtime.snapshot)
    """
    config = EventuallyConfig(
        timeout=timeout,
        poll=poll,
        max_retries=max_retries,
        snapshot_limit_growth=snapshot_limit_growth,
    )
    return EventuallyWrapper(predicate, config)
