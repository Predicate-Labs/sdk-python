"""
Unit-test-only stubs.

The core Sentience SDK imports Playwright at module import time (`sentience.browser`),
but many unit tests don't actually need a real browser. In CI and developer envs,
Playwright is usually installed; however in constrained environments it may not be.

This conftest provides minimal `playwright.*` stubs so we can import the SDK and run
pure unit/contract tests without requiring Playwright.

IMPORTANT:
- These stubs are only active during pytest runs (via conftest import order).
- Integration/E2E tests that need real Playwright should install Playwright and will
  typically run in separate environments.
"""

from __future__ import annotations

import sys
import types


def _ensure_module(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Create top-level playwright module and submodules
playwright_mod = _ensure_module("playwright")
async_api_mod = _ensure_module("playwright.async_api")
sync_api_mod = _ensure_module("playwright.sync_api")


class _Dummy:
    """Placeholder type used for Playwright classes in unit tests."""


# Minimal symbols imported by `sentience.browser`
async_api_mod.BrowserContext = _Dummy
async_api_mod.Browser = _Dummy
async_api_mod.Page = _Dummy
async_api_mod.Playwright = _Dummy
async_api_mod.PlaywrightContextManager = _Dummy


async def _async_playwright():
    raise RuntimeError("Playwright is not available in this unit-test environment.")


async_api_mod.async_playwright = _async_playwright

sync_api_mod.BrowserContext = _Dummy
sync_api_mod.Browser = _Dummy
sync_api_mod.Page = _Dummy
sync_api_mod.Playwright = _Dummy
sync_api_mod.PlaywrightContextManager = _Dummy


def _sync_playwright():
    raise RuntimeError("Playwright is not available in this unit-test environment.")


sync_api_mod.sync_playwright = _sync_playwright


# Expose submodules on the top-level module for completeness
playwright_mod.async_api = async_api_mod
playwright_mod.sync_api = sync_api_mod
