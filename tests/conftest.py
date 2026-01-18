"""
Pytest configuration and fixtures for Sentience SDK tests
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers",
        "requires_extension: mark test as requiring the sentience-chrome extension",
    )


@pytest.fixture
def headless():
    """Fixture that returns headless mode based on CI environment"""
    # In CI, always use headless mode (no X server available)
    # Locally, default to False (headed) for better debugging
    return os.getenv("CI", "").lower() in ("true", "1", "yes")


@pytest.fixture(scope="session")
def extension_available():
    """Check if the sentience-chrome extension is available"""
    # Check if extension exists
    # __file__ is sdk-python/tests/conftest.py
    # parent = sdk-python/tests/
    # parent.parent = sdk-python/
    # parent.parent.parent = Sentience/ (project root)
    repo_root = Path(__file__).parent.parent.parent
    extension_source = repo_root / "sentience-chrome"

    # Also check for required extension files
    if extension_source.exists():
        required_files = ["manifest.json", "content.js", "injected_api.js"]
        pkg_dir = extension_source / "pkg"
        if pkg_dir.exists():
            # Check if WASM files exist
            wasm_files = ["sentience_core.js", "sentience_core_bg.wasm"]
            all_exist = all((extension_source / f).exists() for f in required_files) and all(
                (pkg_dir / f).exists() for f in wasm_files
            )
            return all_exist

    return False


def _ensure_playwright_stubs() -> None:
    """
    Provide minimal `playwright.*` stubs so the SDK can be imported in environments
    where Playwright isn't installed (e.g., constrained CI/sandbox).

    This is only intended to support pure unit/contract tests that don't actually
    launch browsers.
    """

    import sys
    import types

    def ensure_module(name: str) -> types.ModuleType:
        if name in sys.modules:
            return sys.modules[name]
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    playwright_mod = ensure_module("playwright")
    async_api_mod = ensure_module("playwright.async_api")
    sync_api_mod = ensure_module("playwright.sync_api")
    impl_mod = ensure_module("playwright._impl")
    impl_errors_mod = ensure_module("playwright._impl._errors")

    class _Dummy:
        pass

    async_api_mod.BrowserContext = _Dummy
    async_api_mod.Page = _Dummy
    async_api_mod.Playwright = _Dummy

    async def _async_playwright():
        raise RuntimeError("Playwright is not available in this environment.")

    async_api_mod.async_playwright = _async_playwright

    sync_api_mod.BrowserContext = _Dummy
    sync_api_mod.Page = _Dummy
    sync_api_mod.Playwright = _Dummy

    def _sync_playwright():
        raise RuntimeError("Playwright is not available in this environment.")

    sync_api_mod.sync_playwright = _sync_playwright

    playwright_mod.async_api = async_api_mod
    playwright_mod.sync_api = sync_api_mod

    # Some unit tests import internal Playwright exceptions directly
    class TimeoutError(Exception):
        pass

    impl_errors_mod.TimeoutError = TimeoutError
    impl_mod._errors = impl_errors_mod


try:
    import playwright  # noqa: F401

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False
    _ensure_playwright_stubs()


@pytest.fixture(autouse=True)
def skip_if_no_extension(request, extension_available):
    """Automatically skip tests that require extension if it's not available"""
    # Check if test is marked as requiring extension
    marker = request.node.get_closest_marker("requires_extension")

    if marker and not extension_available:
        # In CI, skip silently
        # Otherwise, show a helpful message
        if os.getenv("CI"):
            pytest.skip("Extension not available in CI environment")
        else:
            pytest.skip("Extension not found. Build it first: cd ../sentience-chrome && ./build.sh")


@pytest.fixture(autouse=True)
def skip_non_unit_if_no_playwright(request):
    """
    If Playwright isn't installed, skip non-unit tests.

    Rationale: many tests (and the SDK import surface) depend on Playwright; without it,
    importing those tests will fail during collection. Unit tests can still run using
    lightweight stubs.
    """

    if PLAYWRIGHT_AVAILABLE:
        return

    # Allow unit tests to run (tests/unit/**)
    fspath = str(getattr(request.node, "fspath", ""))
    if "/tests/unit/" in fspath.replace("\\", "/"):
        return

    pytest.skip("Playwright not installed; skipping non-unit tests.")
