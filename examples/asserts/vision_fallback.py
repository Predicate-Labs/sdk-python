"""
v2 (Python-only): vision fallback after snapshot exhaustion.

When `min_confidence` gating keeps failing (snapshot_exhausted), you can pass a
vision-capable LLMProvider to `eventually()` and ask it for a strict YES/NO
verification using a screenshot.

Env vars:
  - OPENAI_API_KEY (if using OpenAIProvider)
  - SENTIENCE_API_KEY (optional, recommended so diagnostics/confidence is present)
"""

import asyncio
import os

from predicate import AgentRuntime, AsyncSentienceBrowser
from predicate.llm_provider import OpenAIProvider
from predicate.tracing import JsonlTraceSink, Tracer
from predicate.verification import exists


async def main() -> None:
    tracer = Tracer(
        run_id="asserts-v2-vision", sink=JsonlTraceSink("trace_asserts_v2_vision.jsonl")
    )
    sentience_api_key = os.getenv("SENTIENCE_API_KEY")

    # Any provider implementing supports_vision() + generate_with_image() works.
    vision = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")

    async with AsyncSentienceBrowser(headless=True) as browser:
        page = await browser.new_page()
        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser, page=page, tracer=tracer
        )
        if sentience_api_key:
            runtime.sentience_api_key = sentience_api_key

        await page.goto("https://example.com")
        runtime.begin_step("Assert v2 vision fallback")

        ok = await runtime.check(
            exists("text~'Example Domain'"), label="example_domain_text"
        ).eventually(
            timeout_s=10.0,
            poll_s=0.25,
            min_confidence=0.7,
            max_snapshot_attempts=2,
            vision_provider=vision,
            vision_system_prompt="You are a strict visual verifier. Answer only YES or NO.",
            vision_user_prompt="In the screenshot, is the phrase 'Example Domain' visible? Answer YES or NO.",
        )

        print("eventually() w/ vision result:", ok)


if __name__ == "__main__":
    asyncio.run(main())
