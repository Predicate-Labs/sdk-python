"""
Pytest configuration and fixtures for Sentience SDK tests
"""

import os
from pathlib import Path

import pytest


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "requires_extension: mark test as requiring the sentience-chrome extension"
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
