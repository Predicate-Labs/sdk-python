"""
Example: Agent Runtime with Verification Loop

Demonstrates how to use AgentRuntime for runtime verification in agent loops.
The AgentRuntime provides assertion predicates to verify browser state during execution.

Key features:
- BrowserBackendV0 protocol: Framework-agnostic browser integration
- Predicate helpers: url_matches, url_contains, exists, not_exists, element_count
- Combinators: all_of, any_of for complex conditions
- Task completion: assert_done() for goal verification
- Trace integration: Assertions emitted to trace for Studio timeline

Requirements:
- SENTIENCE_API_KEY (Pro or Enterprise tier) - optional, enables Gateway refinement

Usage:
    python examples/agent_runtime_verification.py
"""

import asyncio
import os

from sentience import AsyncSentienceBrowser
from sentience.agent_runtime import AgentRuntime
from sentience.tracing import JsonlTraceSink, Tracer
from sentience.verification import all_of, exists, not_exists, url_contains, url_matches


async def main():
    # Get API key from environment (optional - enables Pro tier features)
    sentience_key = os.environ.get("SENTIENCE_API_KEY")

    print("Starting Agent Runtime Verification Demo\n")

    # 1. Create tracer for verification event emission
    run_id = "verification-demo"
    sink = JsonlTraceSink(f"traces/{run_id}.jsonl")
    tracer = Tracer(run_id=run_id, sink=sink)
    print(f"Run ID: {run_id}\n")

    # 2. Create browser using AsyncSentienceBrowser
    async with AsyncSentienceBrowser(headless=False) as browser:
        page = await browser.new_page()

        # 3. Create AgentRuntime using from_sentience_browser factory
        # This wraps the browser/page into the new BrowserBackendV0 architecture
        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser,
            page=page,
            tracer=tracer,
            sentience_api_key=sentience_key,  # Optional: enables Pro tier Gateway refinement
        )

        # 4. Navigate to a page
        print("Navigating to example.com...\n")
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")

        # 5. Begin a verification step
        runtime.begin_step("Verify page loaded correctly")

        # 6. Take a snapshot (required for element assertions)
        snapshot = await runtime.snapshot()
        print(f"Snapshot taken: {len(snapshot.elements)} elements found\n")

        # 7. Run assertions against current state
        print("Running assertions:\n")

        # URL assertions
        url_ok = runtime.assert_(url_contains("example.com"), "on_example_domain")
        print(f"  [{'PASS' if url_ok else 'FAIL'}] on_example_domain")

        url_match = runtime.assert_(url_matches(r"https://.*example\.com"), "url_is_https")
        print(f"  [{'PASS' if url_match else 'FAIL'}] url_is_https")

        # Element assertions
        has_heading = runtime.assert_(exists("role=heading"), "has_heading")
        print(f"  [{'PASS' if has_heading else 'FAIL'}] has_heading")

        no_error = runtime.assert_(not_exists("text~'Error'"), "no_error_message")
        print(f"  [{'PASS' if no_error else 'FAIL'}] no_error_message")

        # Combined assertion with all_of
        page_ready = runtime.assert_(
            all_of(url_contains("example"), exists("role=link")),
            "page_fully_ready",
        )
        print(f"  [{'PASS' if page_ready else 'FAIL'}] page_fully_ready")

        # 8. Check if task is done (required assertion)
        task_complete = runtime.assert_done(
            exists("text~'Example Domain'"),
            "reached_example_page",
        )
        print(f"\n  [{'DONE' if task_complete else 'NOT DONE'}] reached_example_page")

        # 9. Get accumulated assertions for step_end event
        assertions_data = runtime.get_assertions_for_step_end()
        print(f"\nTotal assertions: {len(assertions_data['assertions'])}")
        print(f"Task done: {assertions_data.get('task_done', False)}")

        # 10. Check overall status
        print("\nVerification Summary:")
        print(f"  All passed: {runtime.all_assertions_passed()}")
        print(f"  Required passed: {runtime.required_assertions_passed()}")
        print(f"  Task complete: {runtime.is_task_done}")

    # Close tracer after browser context exits
    print("\nClosing tracer...")
    tracer.close()
    print(f"Trace saved to: traces/{run_id}.jsonl")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
