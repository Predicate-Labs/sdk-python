"""
Example: PydanticAI + Sentience self-correcting action loop using URL guards.

Run:
  pip install predicate-runtime[pydanticai]
  python examples/pydantic_ai/pydantic_ai_self_correcting_click.py
"""

from __future__ import annotations

from predicate import AsyncSentienceBrowser
from predicate.integrations.pydanticai import SentiencePydanticDeps, register_sentience_tools


async def main() -> None:
    from pydantic_ai import Agent

    browser = AsyncSentienceBrowser(headless=False)
    await browser.start()
    await browser.page.goto("https://example.com")  # replace with a real target

    agent = Agent(
        "openai:gpt-5",
        deps_type=SentiencePydanticDeps,
        output_type=str,
        instructions=(
            "Navigate on the site and click the appropriate link/button. "
            "After clicking, use assert_eventually_url_matches to confirm the URL changed as expected."
        ),
    )
    register_sentience_tools(agent)

    deps = SentiencePydanticDeps(browser=browser)
    result = await agent.run("Click something that navigates, then confirm URL changed.", deps=deps)
    print(result.output)

    await browser.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
