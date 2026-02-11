from __future__ import annotations

import pytest


def test_deepinfra_provider_supports_vision_for_common_multimodal_names() -> None:
    pytest.importorskip("openai")

    from predicate.llm_provider import DeepInfraProvider

    p1 = DeepInfraProvider(api_key="x", model="meta-llama/Llama-3.2-11B-Vision-Instruct")
    assert p1.supports_vision() is True

    p2 = DeepInfraProvider(api_key="x", model="deepseek-ai/DeepSeek-OCR")
    assert p2.supports_vision() is True

    p3 = DeepInfraProvider(api_key="x", model="deepseek-ai/DeepSeek-V3.1")
    assert p3.supports_vision() is False

