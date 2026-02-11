"""
Verification primitives for agent assertion loops.

This module provides assertion predicates and outcome types for runtime verification
in agent loops. Assertions evaluate against the current browser state (snapshot/url)
and record results into the trace.

Key concepts:
- AssertOutcome: Result of evaluating an assertion
- AssertContext: Context provided to assertion predicates (snapshot, url, step_id)
- Predicate: Callable that takes context and returns outcome

Example usage:
    from predicate.verification import url_matches, exists, AssertContext

    # Create predicates
    on_search_page = url_matches(r"/s\\?k=")
    results_loaded = exists("text~'Results'")

    # Evaluate against context
    ctx = AssertContext(snapshot=snapshot, url="https://example.com/s?k=shoes")
    outcome = on_search_page(ctx)
    print(outcome.passed)  # True
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Snapshot


@dataclass
class AssertOutcome:
    """
    Result of evaluating an assertion predicate.

    Attributes:
        passed: Whether the assertion passed
        reason: Human-readable explanation (especially useful when failed)
        details: Additional structured data for debugging/display
    """

    passed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssertContext:
    """
    Context provided to assertion predicates.

    Provides access to current browser state without requiring
    the predicate to know about browser internals.

    Attributes:
        snapshot: Current page snapshot (may be None if not taken)
        url: Current page URL
        step_id: Current step identifier (for trace correlation)
    """

    snapshot: Snapshot | None = None
    url: str | None = None
    step_id: str | None = None
    # Optional: non-snapshot state signals for verification (e.g., downloads).
    downloads: list[dict[str, Any]] | None = None


# Type alias for assertion predicates
Predicate = Callable[[AssertContext], AssertOutcome]


def download_completed(filename_substring: str | None = None) -> Predicate:
    """
    Predicate that passes if a browser download has completed.

    Notes:
    - This relies on `AssertContext.downloads` being populated by the runtime/backend.
    - For PlaywrightBackend, downloads are tracked automatically when possible.
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        downloads = ctx.downloads or []
        for d in downloads:
            if str(d.get("status") or "") != "completed":
                continue
            fname = str(d.get("filename") or d.get("suggested_filename") or "")
            if filename_substring is None or (filename_substring in fname):
                return AssertOutcome(passed=True, reason="", details={"download": d})
        return AssertOutcome(
            passed=False,
            reason=(
                f"no completed download matched: {filename_substring}"
                if filename_substring
                else "no completed downloads"
            ),
            details={"filename_substring": filename_substring, "downloads": downloads},
        )

    return _pred


def url_matches(pattern: str) -> Predicate:
    """
    Create a predicate that checks if current URL matches a regex pattern.

    Args:
        pattern: Regular expression pattern to match against URL

    Returns:
        Predicate function that evaluates URL matching

    Example:
        >>> pred = url_matches(r"/search\\?q=")
        >>> ctx = AssertContext(url="https://example.com/search?q=shoes")
        >>> outcome = pred(ctx)
        >>> outcome.passed
        True
    """
    rx = re.compile(pattern)

    def _pred(ctx: AssertContext) -> AssertOutcome:
        url = ctx.url or ""
        ok = rx.search(url) is not None
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"url did not match pattern: {pattern}",
            details={"pattern": pattern, "url": url[:200]},
        )

    return _pred


def url_contains(substring: str) -> Predicate:
    """
    Create a predicate that checks if current URL contains a substring.

    Args:
        substring: String to search for in URL

    Returns:
        Predicate function that evaluates URL containment

    Example:
        >>> pred = url_contains("/cart")
        >>> ctx = AssertContext(url="https://example.com/cart/checkout")
        >>> outcome = pred(ctx)
        >>> outcome.passed
        True
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        url = ctx.url or ""
        ok = substring in url
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"url does not contain: {substring}",
            details={"substring": substring, "url": url[:200]},
        )

    return _pred


def exists(selector: str) -> Predicate:
    """
    Create a predicate that checks if elements matching selector exist.

    Uses the SDK's query engine to find matching elements.

    Args:
        selector: Semantic selector string (e.g., "role=button text~'Sign in'")

    Returns:
        Predicate function that evaluates element existence

    Example:
        >>> pred = exists("text~'Results'")
        >>> # Will check if snapshot contains elements with "Results" in text
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False,
                reason="no snapshot available",
                details={"selector": selector, "reason_code": "no_snapshot"},
            )

        # Import here to avoid circular imports
        from .query import query

        matches = query(snap, selector)
        ok = len(matches) > 0
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"no elements matched selector: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "no_match",
            },
        )

    return _pred


def not_exists(selector: str) -> Predicate:
    """
    Create a predicate that checks that NO elements match the selector.

    Useful for asserting that error messages, loading spinners, etc. are gone.

    Args:
        selector: Semantic selector string

    Returns:
        Predicate function that evaluates element non-existence

    Example:
        >>> pred = not_exists("text~'Loading'")
        >>> # Will pass if no elements contain "Loading" text
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False,
                reason="no snapshot available",
                details={"selector": selector, "reason_code": "no_snapshot"},
            )

        from .query import query

        matches = query(snap, selector)
        ok = len(matches) == 0
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"found {len(matches)} elements matching: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "unexpected_match",
            },
        )

    return _pred


def element_count(selector: str, *, min_count: int = 0, max_count: int | None = None) -> Predicate:
    """
    Create a predicate that checks the number of matching elements.

    Args:
        selector: Semantic selector string
        min_count: Minimum number of matches required (inclusive)
        max_count: Maximum number of matches allowed (inclusive, None = no limit)

    Returns:
        Predicate function that evaluates element count

    Example:
        >>> pred = element_count("role=button", min_count=1, max_count=5)
        >>> # Will pass if 1-5 buttons found
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False,
                reason="no snapshot available",
                details={"selector": selector, "min_count": min_count, "max_count": max_count},
            )

        from .query import query

        matches = query(snap, selector)
        count = len(matches)

        ok = count >= min_count
        if max_count is not None:
            ok = ok and count <= max_count

        if ok:
            reason = ""
        else:
            if max_count is not None:
                reason = f"expected {min_count}-{max_count} elements, found {count}"
            else:
                reason = f"expected at least {min_count} elements, found {count}"

        return AssertOutcome(
            passed=ok,
            reason=reason,
            details={
                "selector": selector,
                "matched": count,
                "min_count": min_count,
                "max_count": max_count,
            },
        )

    return _pred


def all_of(*predicates: Predicate) -> Predicate:
    """
    Create a predicate that passes only if ALL sub-predicates pass.

    Args:
        *predicates: Predicate functions to combine with AND logic

    Returns:
        Combined predicate

    Example:
        >>> pred = all_of(url_contains("/cart"), exists("text~'Checkout'"))
        >>> # Will pass only if both conditions are true
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        failed_reasons = []
        all_details: list[dict[str, Any]] = []

        for p in predicates:
            outcome = p(ctx)
            all_details.append(outcome.details)
            if not outcome.passed:
                failed_reasons.append(outcome.reason)

        ok = len(failed_reasons) == 0
        return AssertOutcome(
            passed=ok,
            reason="; ".join(failed_reasons) if failed_reasons else "",
            details={"sub_predicates": all_details, "failed_count": len(failed_reasons)},
        )

    return _pred


def any_of(*predicates: Predicate) -> Predicate:
    """
    Create a predicate that passes if ANY sub-predicate passes.

    Args:
        *predicates: Predicate functions to combine with OR logic

    Returns:
        Combined predicate

    Example:
        >>> pred = any_of(exists("text~'Success'"), exists("text~'Complete'"))
        >>> # Will pass if either condition is true
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        all_reasons = []
        all_details: list[dict[str, Any]] = []

        for p in predicates:
            outcome = p(ctx)
            all_details.append(outcome.details)
            if outcome.passed:
                return AssertOutcome(
                    passed=True,
                    reason="",
                    details={
                        "sub_predicates": all_details,
                        "matched_at_index": len(all_details) - 1,
                    },
                )
            all_reasons.append(outcome.reason)

        return AssertOutcome(
            passed=False,
            reason=f"none of {len(predicates)} predicates passed: " + "; ".join(all_reasons),
            details={"sub_predicates": all_details},
        )

    return _pred


def custom(check_fn: Callable[[AssertContext], bool], label: str = "custom") -> Predicate:
    """
    Create a predicate from a custom function.

    Args:
        check_fn: Function that takes AssertContext and returns bool
        label: Label for debugging/display

    Returns:
        Predicate wrapping the custom function

    Example:
        >>> pred = custom(lambda ctx: ctx.snapshot and len(ctx.snapshot.elements) > 10, "has_many_elements")
    """

    def _pred(ctx: AssertContext) -> AssertOutcome:
        try:
            ok = check_fn(ctx)
            return AssertOutcome(
                passed=ok,
                reason="" if ok else f"custom check '{label}' returned False",
                details={"label": label},
            )
        except Exception as e:
            return AssertOutcome(
                passed=False,
                reason=f"custom check '{label}' raised exception: {e}",
                details={"label": label, "error": str(e)},
            )

    return _pred


# ============================================================================
# v1 state-aware predicates (deterministic, schema-driven)
# ============================================================================


def is_enabled(selector: str) -> Predicate:
    """Passes if any matched element is not disabled (disabled=None treated as enabled)."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        if not matches:
            return AssertOutcome(
                passed=False,
                reason=f"no elements matched selector: {selector}",
                details={"selector": selector, "matched": 0, "reason_code": "no_match"},
            )

        ok = any(m.disabled is not True for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"all matched elements are disabled: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def is_disabled(selector: str) -> Predicate:
    """Passes if any matched element is disabled."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any(m.disabled is True for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"no matched elements are disabled: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def is_checked(selector: str) -> Predicate:
    """Passes if any matched element is checked."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any(m.checked is True for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"no matched elements are checked: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def is_unchecked(selector: str) -> Predicate:
    """Passes if any matched element is not checked (checked=None treated as unchecked)."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any(m.checked is not True for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"all matched elements are checked: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def value_equals(selector: str, expected: str) -> Predicate:
    """Passes if any matched element has value exactly equal to expected."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any((m.value or "") == expected for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"no matched elements had value == '{expected}'",
            details={
                "selector": selector,
                "expected": expected,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def value_contains(selector: str, substring: str) -> Predicate:
    """Passes if any matched element value contains substring (case-insensitive)."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any(substring.lower() in (m.value or "").lower() for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"no matched elements had value containing '{substring}'",
            details={
                "selector": selector,
                "substring": substring,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def is_expanded(selector: str) -> Predicate:
    """Passes if any matched element is expanded."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any(m.expanded is True for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"no matched elements are expanded: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred


def is_collapsed(selector: str) -> Predicate:
    """Passes if any matched element is not expanded (expanded=None treated as collapsed)."""

    def _pred(ctx: AssertContext) -> AssertOutcome:
        snap = ctx.snapshot
        if snap is None:
            return AssertOutcome(
                passed=False, reason="no snapshot available", details={"selector": selector}
            )

        from .query import query

        matches = query(snap, selector)
        ok = any(m.expanded is not True for m in matches)
        return AssertOutcome(
            passed=ok,
            reason="" if ok else f"all matched elements are expanded: {selector}",
            details={
                "selector": selector,
                "matched": len(matches),
                "reason_code": "ok" if ok else "state_mismatch",
            },
        )

    return _pred
