"""
Browser Use integration (Predicate plugin).

This package provides a low-friction integration layer that lets browser-use users
attach Predicate's deterministic verification (AgentRuntime / PredicateDebugger)
to existing Browser Use agent loops via lifecycle hooks and optional tools.

Public surface is intentionally small and may evolve.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .plugin import (
        PredicateBrowserUsePlugin,
        PredicateBrowserUsePluginConfig,
        PredicateBrowserUseVerificationError,
        StepCheckSpec,
    )

__all__ = [
    "PredicateBrowserUsePlugin",
    "PredicateBrowserUsePluginConfig",
    "PredicateBrowserUseVerificationError",
    "StepCheckSpec",
]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name in __all__:
        from .plugin import (  # local import keeps linting/packaging robust
            PredicateBrowserUsePlugin,
            PredicateBrowserUsePluginConfig,
            PredicateBrowserUseVerificationError,
            StepCheckSpec,
        )

        return {
            "PredicateBrowserUsePlugin": PredicateBrowserUsePlugin,
            "PredicateBrowserUsePluginConfig": PredicateBrowserUsePluginConfig,
            "PredicateBrowserUseVerificationError": PredicateBrowserUseVerificationError,
            "StepCheckSpec": StepCheckSpec,
        }[name]
    raise AttributeError(name)

