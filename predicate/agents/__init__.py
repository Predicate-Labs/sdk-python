"""
Agent-level orchestration helpers (snapshot-first, verification-first).

This package provides a "browser-use-like" agent surface built on top of:
- AgentRuntime (snapshots, verification, tracing)
- RuntimeAgent (execution loop and bounded vision fallback)
"""

from .browser_agent import (
    CaptchaConfig,
    PermissionRecoveryConfig,
    PredicateBrowserAgent,
    PredicateBrowserAgentConfig,
    VisionFallbackConfig,
)

__all__ = [
    "CaptchaConfig",
    "PermissionRecoveryConfig",
    "PredicateBrowserAgent",
    "PredicateBrowserAgentConfig",
    "VisionFallbackConfig",
]

