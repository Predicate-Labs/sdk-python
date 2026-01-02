"""
LLM Provider utility functions for common initialization and error handling.

This module provides helper functions to reduce duplication across LLM provider implementations.
"""

import os
from collections.abc import Callable
from typing import Any, Optional, TypeVar

T = TypeVar("T")


def require_package(
    package_name: str,
    module_name: str,
    class_name: str | None = None,
    install_command: str | None = None,
) -> Any:
    """
    Import a package with consistent error handling.

    Args:
        package_name: Name of the package (for error messages)
        module_name: Module name to import (e.g., "openai", "google.generativeai")
        class_name: Optional class name to import from module (e.g., "OpenAI")
        install_command: Installation command (defaults to "pip install {package_name}")

    Returns:
        Imported module or class

    Raises:
        ImportError: If package is not installed, with helpful message

    Example:
        >>> OpenAI = require_package("openai", "openai", "OpenAI", "pip install openai")
        >>> genai = require_package("google-generativeai", "google.generativeai", install_command="pip install google-generativeai")
    """
    if install_command is None:
        install_command = f"pip install {package_name}"

    try:
        if class_name:
            # Import specific class: from module import class
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        else:
            # Import entire module
            return __import__(module_name)
    except ImportError:
        raise ImportError(f"{package_name} package not installed. Install with: {install_command}")


def get_api_key_from_env(
    env_vars: list[str],
    api_key: str | None = None,
) -> str | None:
    """
    Get API key from parameter or environment variables.

    Args:
        env_vars: List of environment variable names to check (in order)
        api_key: Optional API key parameter (takes precedence)

    Returns:
        API key string or None if not found

    Example:
        >>> key = get_api_key_from_env(["OPENAI_API_KEY"], api_key="sk-...")
        >>> # Returns "sk-..." if provided, otherwise checks OPENAI_API_KEY env var
    """
    if api_key:
        return api_key

    for env_var in env_vars:
        value = os.getenv(env_var)
        if value:
            return value

    return None


def handle_provider_error(
    error: Exception,
    provider_name: str,
    operation: str = "operation",
) -> None:
    """
    Standardize error handling for LLM provider operations.

    Args:
        error: Exception that occurred
        provider_name: Name of the provider (e.g., "OpenAI", "Anthropic")
        operation: Description of the operation that failed

    Raises:
        RuntimeError: With standardized error message

    Example:
        >>> try:
        ...     response = client.chat.completions.create(...)
        ... except Exception as e:
        ...     handle_provider_error(e, "OpenAI", "generate response")
    """
    error_msg = str(error)
    if "api key" in error_msg.lower() or "authentication" in error_msg.lower():
        raise RuntimeError(
            f"{provider_name} API key is invalid or missing. "
            f"Please check your API key configuration."
        ) from error
    elif "rate limit" in error_msg.lower() or "429" in error_msg:
        raise RuntimeError(
            f"{provider_name} rate limit exceeded. Please try again later."
        ) from error
    elif "model" in error_msg.lower() and "not found" in error_msg.lower():
        raise RuntimeError(
            f"{provider_name} model not found. Please check the model name."
        ) from error
    else:
        raise RuntimeError(f"{provider_name} {operation} failed: {error_msg}") from error
