"""
Tests for LLMResponseBuilder helper class.
"""

import pytest

from sentience.llm_provider import LLMResponse
from sentience.llm_response_builder import LLMResponseBuilder


class TestLLMResponseBuilder:
    """Test LLMResponseBuilder helper methods"""

    def test_from_openai_format(self):
        """Test building response from OpenAI format"""
        response = LLMResponseBuilder.from_openai_format(
            content="Hello, world!",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="gpt-4o",
            finish_reason="stop",
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Hello, world!"
        assert response.prompt_tokens == 10
        assert response.completion_tokens == 5
        assert response.total_tokens == 15
        assert response.model_name == "gpt-4o"
        assert response.finish_reason == "stop"

    def test_from_openai_format_auto_total(self):
        """Test OpenAI format with auto-calculated total_tokens"""
        response = LLMResponseBuilder.from_openai_format(
            content="Test",
            prompt_tokens=5,
            completion_tokens=3,
            model_name="gpt-4o",
        )

        assert response.total_tokens == 8  # Auto-calculated

    def test_from_anthropic_format(self):
        """Test building response from Anthropic format"""
        response = LLMResponseBuilder.from_anthropic_format(
            content="Claude response",
            input_tokens=12,
            output_tokens=8,
            model_name="claude-3-sonnet",
            stop_reason="end_turn",
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Claude response"
        assert response.prompt_tokens == 12
        assert response.completion_tokens == 8
        assert response.total_tokens == 20
        assert response.model_name == "claude-3-sonnet"
        assert response.finish_reason == "end_turn"

    def test_from_gemini_format(self):
        """Test building response from Gemini format"""
        response = LLMResponseBuilder.from_gemini_format(
            content="Gemini response",
            prompt_tokens=15,
            completion_tokens=7,
            total_tokens=22,
            model_name="gemini-2.0-flash-exp",
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Gemini response"
        assert response.prompt_tokens == 15
        assert response.completion_tokens == 7
        assert response.total_tokens == 22
        assert response.model_name == "gemini-2.0-flash-exp"
        assert response.finish_reason is None

    def test_from_local_format(self):
        """Test building response from local model format"""
        response = LLMResponseBuilder.from_local_format(
            content="Local model response",
            prompt_tokens=20,
            completion_tokens=10,
            model_name="Qwen/Qwen2.5-3B-Instruct",
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Local model response"
        assert response.prompt_tokens == 20
        assert response.completion_tokens == 10
        assert response.total_tokens == 30
        assert response.model_name == "Qwen/Qwen2.5-3B-Instruct"
        assert response.finish_reason is None

