"""
v1: State-aware assertions with AgentRuntime.

This example is meant to be run with a Pro/Enterprise API key so the Gateway
can refine raw elements into SmartElements with state fields (enabled/checked/value/etc).

Env vars:
  - SENTIENCE_API_KEY (optional but recommended for v1 state assertions)
"""

import asyncio
import os

from predicate import AgentRuntime, AsyncSentienceBrowser
from predicate.tracing import JsonlTraceSink, Tracer
from predicate.verification import (
    exists,
    is_checked,
    is_disabled,
    is_enabled,
    is_expanded,
    value_contains,
)


async def main() -> None:
    tracer = Tracer(run_id="asserts-v1", sink=JsonlTraceSink("trace_asserts_v1.jsonl"))

    sentience_api_key = os.getenv("SENTIENCE_API_KEY")

    async with AsyncSentienceBrowser(headless=True) as browser:
        page = await browser.new_page()
        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser, page=page, tracer=tracer
        )

        # If you have a Pro/Enterprise key, set it on the runtime so snapshots use the Gateway.
        # (This improves selector quality and unlocks state-aware fields for assertions.)
        if sentience_api_key:
            runtime.sentience_api_key = sentience_api_key

        await page.goto("https://example.com")
        runtime.begin_step("Assert v1 state")
        await runtime.snapshot()

        # v1: state-aware assertions (examples)
        runtime.assert_(exists("role=heading"), label="has_heading")
        runtime.assert_(is_enabled("role=link"), label="some_link_enabled")
        runtime.assert_(
            is_disabled("role=button text~'continue'"), label="continue_disabled_if_present"
        )
        runtime.assert_(
            is_checked("role=checkbox name~'subscribe'"), label="subscribe_checked_if_present"
        )
        runtime.assert_(is_expanded("role=button name~'more'"), label="more_is_expanded_if_present")
        runtime.assert_(
            value_contains("role=textbox name~'email'", "@"), label="email_has_at_if_present"
        )

        # Failure intelligence: if something fails you’ll see:
        # - details.reason_code
        # - details.nearest_matches (suggestions)

        print("Assertions recorded:", runtime.get_assertions_for_step_end()["assertions"])


if __name__ == "__main__":
    asyncio.run(main())
