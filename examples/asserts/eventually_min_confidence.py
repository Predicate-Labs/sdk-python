"""
v2: `.check(...).eventually(...)` with snapshot confidence gating + exhaustion.

This example shows:
- retry loop semantics
- `min_confidence` gating (snapshot_low_confidence -> snapshot_exhausted)
- structured assertion records in traces
"""

import asyncio
import os

from sentience import AgentRuntime, AsyncSentienceBrowser
from sentience.tracing import JsonlTraceSink, Tracer
from sentience.verification import exists


async def main() -> None:
    tracer = Tracer(run_id="asserts-v2", sink=JsonlTraceSink("trace_asserts_v2.jsonl"))
    sentience_api_key = os.getenv("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(headless=True) as browser:
        page = await browser.new_page()
        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser, page=page, tracer=tracer
        )
        if sentience_api_key:
            runtime.sentience_api_key = sentience_api_key

        await page.goto("https://example.com")
        runtime.begin_step("Assert v2 eventually")

        ok = await runtime.check(
            exists("role=heading"),
            label="heading_eventually_visible",
            required=True,
        ).eventually(
            timeout_s=10.0,
            poll_s=0.25,
            # If the Gateway reports snapshot.diagnostics.confidence, gate on it:
            min_confidence=0.7,
            max_snapshot_attempts=3,
        )

        print("eventually() result:", ok)
        print("Final assertion:", runtime.get_assertions_for_step_end()["assertions"])


if __name__ == "__main__":
    asyncio.run(main())
