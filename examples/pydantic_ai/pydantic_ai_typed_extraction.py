"""
Example: PydanticAI + Sentience typed extraction (Phase 1 integration).

Run:
  pip install sentienceapi[pydanticai]
  python examples/pydantic_ai/pydantic_ai_typed_extraction.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sentience import AsyncSentienceBrowser
from sentience.integrations.pydanticai import SentiencePydanticDeps, register_sentience_tools


class ProductInfo(BaseModel):
    title: str = Field(..., description="Product title")
    price: str = Field(..., description="Displayed price string")


async def main() -> None:
    from pydantic_ai import Agent

    browser = AsyncSentienceBrowser(headless=False)
    await browser.start()
    await browser.page.goto("https://example.com")  # replace with a real target

    agent = Agent(
        "openai:gpt-5",
        deps_type=SentiencePydanticDeps,
        output_type=ProductInfo,
        instructions="Extract the product title and price from the page.",
    )
    register_sentience_tools(agent)

    deps = SentiencePydanticDeps(browser=browser)
    result = await agent.run("Extract title and price.", deps=deps)
    print(result.output)

    await browser.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

