from __future__ import annotations

import pytest
from pydantic import BaseModel

from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.read import extract


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


class PageStub:
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


class AsyncPageStub:
    def __init__(self, content: str):
        self._content = content

    async def evaluate(self, _script: str, _opts: dict):
        return {
            "status": "success",
            "url": "https://example.com",
            "format": "markdown",
            "content": self._content,
            "length": len(self._content),
        }


class BrowserStub:
    def __init__(self, content: str):
        self.page = PageStub(content)


class AsyncBrowserStub:
    def __init__(self, content: str):
        self.page = AsyncPageStub(content)


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
    browser = AsyncBrowserStub("Product: Widget")
    llm = LLMStub('{"name":"Widget","price":"$10"}')
    from predicate.read import extract_async

    result = await extract_async(browser, llm, query="Extract item", schema=ItemSchema)
    assert result.ok is True
    assert result.data is not None
    assert result.data.name == "Widget"
