"""Tests for sentience.llm_provider_utils module"""

import os
from unittest.mock import patch

import pytest

from sentience.llm_provider_utils import (
    get_api_key_from_env,
    handle_provider_error,
    require_package,
)


def test_require_package_success():
    """Test require_package successfully imports existing package."""
    # Test with a package that should exist
    json_module = require_package("json", "json", install_command="pip install json")
    assert json_module is not None
    # Verify it's actually the json module
    assert hasattr(json_module, "dumps")


def test_require_package_import_error():
    """Test require_package raises ImportError for missing package."""
    with pytest.raises(ImportError, match="nonexistent-package.*not installed"):
        require_package(
            "nonexistent-package",
            "nonexistent_package",
            install_command="pip install nonexistent-package",
        )


def test_require_package_with_class():
    """Test require_package imports specific class."""
    # json doesn't have a class, but we can test the mechanism
    json_module = require_package("json", "json", install_command="pip install json")
    assert json_module is not None


def test_get_api_key_from_env_with_param():
    """Test get_api_key_from_env returns parameter if provided."""
    key = get_api_key_from_env(["TEST_API_KEY"], api_key="provided-key")
    assert key == "provided-key"


def test_get_api_key_from_env_from_env_var():
    """Test get_api_key_from_env reads from environment variable."""
    with patch.dict(os.environ, {"TEST_API_KEY": "env-key-value"}):
        key = get_api_key_from_env(["TEST_API_KEY"])
        assert key == "env-key-value"


def test_get_api_key_from_env_multiple_vars():
    """Test get_api_key_from_env checks multiple environment variables."""
    # Remove FIRST_KEY if it exists, set SECOND_KEY
    with patch.dict(os.environ, {"SECOND_KEY": "second-value"}, clear=False):
        # Remove FIRST_KEY if it exists
        os.environ.pop("FIRST_KEY", None)
        key = get_api_key_from_env(["FIRST_KEY", "SECOND_KEY"])
        assert key == "second-value"


def test_get_api_key_from_env_not_found():
    """Test get_api_key_from_env returns None if not found."""
    with patch.dict(os.environ, {}, clear=True):
        key = get_api_key_from_env(["NONEXISTENT_KEY"])
        assert key is None


def test_handle_provider_error_api_key():
    """Test handle_provider_error handles API key errors."""
    error = Exception("Invalid API key provided")
    with pytest.raises(RuntimeError, match="API key is invalid or missing"):
        handle_provider_error(error, "OpenAI", "generate response")


def test_handle_provider_error_rate_limit():
    """Test handle_provider_error handles rate limit errors."""
    error = Exception("Rate limit exceeded: 429")
    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        handle_provider_error(error, "Anthropic", "generate response")


def test_handle_provider_error_model_not_found():
    """Test handle_provider_error handles model not found errors."""
    error = Exception("Model 'gpt-999' not found")
    with pytest.raises(RuntimeError, match="model not found"):
        handle_provider_error(error, "OpenAI", "generate response")


def test_handle_provider_error_generic():
    """Test handle_provider_error handles generic errors."""
    error = Exception("Network timeout")
    with pytest.raises(RuntimeError, match="Gemini generate response failed: Network timeout"):
        handle_provider_error(error, "Gemini", "generate response")

