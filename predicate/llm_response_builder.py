"""
LLM Response building utilities for consistent response construction.

This module provides helper functions for building LLMResponse objects
from various provider API responses.
"""

from typing import Any, Optional

# Import LLMResponse here to avoid circular dependency
# We import it inside functions to break the cycle


class LLMResponseBuilder:
    """
    Helper for building LLMResponse objects with consistent structure.

    Provides static methods for building responses from different provider formats.
    """

    @staticmethod
    def from_openai_format(
        content: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        model_name: str | None = None,
        finish_reason: str | None = None,
    ) -> "LLMResponse":
        """
        Build LLMResponse from OpenAI-style API response.

        Args:
            content: Response text content
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            total_tokens: Total tokens (or sum of prompt + completion)
            model_name: Model identifier
            finish_reason: Finish reason (stop, length, etc.)

        Returns:
            LLMResponse object
        """
        from .llm_provider import LLMResponse  # Import here to avoid circular dependency

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens
            or (
                (prompt_tokens + completion_tokens) if prompt_tokens and completion_tokens else None
            ),
            model_name=model_name,
            finish_reason=finish_reason,
        )

    @staticmethod
    def from_anthropic_format(
        content: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model_name: str | None = None,
        stop_reason: str | None = None,
    ) -> "LLMResponse":
        """
        Build LLMResponse from Anthropic-style API response.

        Args:
            content: Response text content
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model_name: Model identifier
            stop_reason: Stop reason (end_turn, max_tokens, etc.)

        Returns:
            LLMResponse object
        """
        from .llm_provider import LLMResponse  # Import here to avoid circular dependency

        return LLMResponse(
            content=content,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=(input_tokens + output_tokens) if input_tokens and output_tokens else None,
            model_name=model_name,
            finish_reason=stop_reason,
        )

    @staticmethod
    def from_gemini_format(
        content: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        model_name: str | None = None,
    ) -> "LLMResponse":
        """
        Build LLMResponse from Gemini-style API response.

        Args:
            content: Response text content
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            total_tokens: Total tokens
            model_name: Model identifier

        Returns:
            LLMResponse object
        """
        from .llm_provider import LLMResponse  # Import here to avoid circular dependency

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens
            or (
                (prompt_tokens + completion_tokens) if prompt_tokens and completion_tokens else None
            ),
            model_name=model_name,
            finish_reason=None,  # Gemini uses different finish reason format
        )

    @staticmethod
    def from_local_format(
        content: str,
        prompt_tokens: int,
        completion_tokens: int,
        model_name: str,
    ) -> "LLMResponse":
        """
        Build LLMResponse from local model generation.

        Args:
            content: Response text content
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            model_name: Model identifier

        Returns:
            LLMResponse object
        """
        from .llm_provider import LLMResponse  # Import here to avoid circular dependency

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model_name=model_name,
            finish_reason=None,
        )
