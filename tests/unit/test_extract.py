from __future__ import annotations

import pytest
from pydantic import BaseModel

from sentience.llm_provider import LLMProvider, LLMResponse
from sentience.read import extract


class LLMStub(LLMProvider):
    def __init__(self, response: str):
        super().__init__("stub")
        self._response = response

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> LLMResponse:
        _ = system_prompt, user_prompt, kwargs
        return LLMResponse(content=self._response, model_name="stub")

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return "stub"


class BrowserStub:
    page = True

    def __init__(self, content: str):
        self._content = content

    def evaluate(self, _script: str, _opts: dict):
        return {
            "status": "success",
            "url": "https://example.com",
            "format": "markdown",
            "content": self._content,
            "length": len(self._content),
        }


class ItemSchema(BaseModel):
    name: str
    price: str


def test_extract_schema_success() -> None:
    browser = BrowserStub("Product: Widget")
    llm = LLMStub('{"name":"Widget","price":"$10"}')
    result = extract(browser, llm, query="Extract item", schema=ItemSchema)
    assert result.ok is True
    assert result.data is not None
    assert result.data.name == "Widget"


def test_extract_schema_invalid_json() -> None:
    browser = BrowserStub("Product: Widget")
    llm = LLMStub("not json")
    result = extract(browser, llm, query="Extract item", schema=ItemSchema)
    assert result.ok is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_extract_async_schema_success() -> None:
    browser = BrowserStub("Product: Widget")
    llm = LLMStub('{"name":"Widget","price":"$10"}')
    from sentience.read import extract_async

    result = await extract_async(browser, llm, query="Extract item", schema=ItemSchema)
    assert result.ok is True
    assert result.data is not None
    assert result.data.name == "Widget"
