"""
Example: Build Sentience LangChain tools (async-only).

Install:
  pip install sentienceapi[langchain]

Run:
  python examples/lang-chain/langchain_tools_demo.py

Notes:
- This example focuses on creating the tools. Hook them into your agent of choice.
"""

from __future__ import annotations

import asyncio

from sentience import AsyncSentienceBrowser
from sentience.integrations.langchain import (
    SentienceLangChainContext,
    build_sentience_langchain_tools,
)


async def main() -> None:
    browser = AsyncSentienceBrowser(headless=False)
    await browser.start()
    await browser.goto("https://example.com")

    ctx = SentienceLangChainContext(browser=browser)
    tools = build_sentience_langchain_tools(ctx)

    print("Registered tools:")
    for t in tools:
        print(f"- {t.name}")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
