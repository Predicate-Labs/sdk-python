"""Compatibility tests for Predicate* class counterparts."""

from predicate import (
    AsyncPredicateBrowser,
    PredicateAgent,
    PredicateAgentAsync,
    PredicateBrowser,
    PredicateDebugger,
    PredicateVisualAgent,
    PredicateVisualAgentAsync,
    AsyncSentienceBrowser,
    SentienceAgent,
    SentienceAgentAsync,
    SentienceBrowser,
    SentienceDebugger,
    SentienceVisualAgent,
    SentienceVisualAgentAsync,
)


def test_predicate_browser_aliases() -> None:
    assert PredicateBrowser is SentienceBrowser
    assert AsyncPredicateBrowser is AsyncSentienceBrowser


def test_predicate_agent_aliases() -> None:
    assert PredicateAgent is SentienceAgent
    assert PredicateAgentAsync is SentienceAgentAsync


def test_predicate_visual_agent_aliases() -> None:
    assert PredicateVisualAgent is SentienceVisualAgent
    assert PredicateVisualAgentAsync is SentienceVisualAgentAsync


def test_predicate_debugger_alias() -> None:
    assert PredicateDebugger is SentienceDebugger
