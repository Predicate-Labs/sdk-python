"""
Assertion DSL for Sentience SDK.

This module provides a Playwright/Cypress-like assertion API for verifying
browser state in agent verification loops.

Main exports:
- E: Element query builder (filters elements by role, text, href, etc.)
- expect: Expectation builder (creates predicates from queries)
- in_dominant_list: Query over dominant group elements (ordinal access)

Example usage:
    from predicate.asserts import E, expect, in_dominant_list

    # Basic presence assertions
    runtime.assert_(
        expect(E(role="button", text_contains="Save")).to_exist(),
        label="save_button_visible"
    )

    # Visibility assertions
    runtime.assert_(
        expect(E(text_contains="Checkout")).to_be_visible(),
        label="checkout_visible"
    )

    # Global text assertions
    runtime.assert_(
        expect.text_present("Welcome back"),
        label="user_logged_in"
    )
    runtime.assert_(
        expect.no_text("Error"),
        label="no_error_message"
    )

    # Ordinal assertions on dominant group
    runtime.assert_(
        expect(in_dominant_list().nth(0)).to_have_text_contains("Show HN"),
        label="first_item_is_show_hn"
    )

    # Task completion
    runtime.assert_done(
        expect.text_present("Order confirmed"),
        label="checkout_complete"
    )

The DSL compiles to existing Predicate functions, so it works seamlessly
with AgentRuntime.assert_() and assert_done().
"""

from .expect import EventuallyConfig, EventuallyWrapper, ExpectBuilder, expect, with_eventually
from .query import E, ElementQuery, ListQuery, MultiQuery, in_dominant_list

__all__ = [
    # Query builders
    "E",
    "ElementQuery",
    "ListQuery",
    "MultiQuery",
    "in_dominant_list",
    # Expectation builders
    "expect",
    "ExpectBuilder",
    # Eventually helpers
    "with_eventually",
    "EventuallyWrapper",
    "EventuallyConfig",
]
