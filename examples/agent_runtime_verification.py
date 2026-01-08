"""
Example: Agent Runtime with Verification Loop

Demonstrates how to use AgentRuntime for runtime verification in agent loops.
The AgentRuntime provides assertion predicates to verify browser state during execution.

Key features:
- Predicate helpers: url_matches, url_contains, exists, not_exists, element_count
- Combinators: all_of, any_of for complex conditions
- Task completion: assert_done() for goal verification
- Trace integration: Assertions emitted to trace for Studio timeline

Requirements:
- SENTIENCE_API_KEY (Pro or Enterprise tier)

Usage:
    python examples/agent_runtime_verification.py
"""

import os

from sentience import (
    AgentRuntime,
    SentienceBrowser,
    all_of,
    exists,
    not_exists,
    url_contains,
    url_matches,
)
from sentience.tracer_factory import create_tracer


def main():
    # Get API key from environment
    sentience_key = os.environ.get("SENTIENCE_API_KEY")

    if not sentience_key:
        print("Error: SENTIENCE_API_KEY not set")
        return

    print("Starting Agent Runtime Verification Demo\n")

    # 1. Create tracer for verification event emission
    run_id = "verification-demo"
    tracer = create_tracer(api_key=sentience_key, run_id=run_id, upload_trace=False)
    print(f"Run ID: {run_id}\n")

    # 2. Create browser
    browser = SentienceBrowser(api_key=sentience_key, headless=False)
    browser.start()

    try:
        # 3. Create AgentRuntime with browser, page, and tracer
        runtime = AgentRuntime(browser, browser.page, tracer)

        # 4. Navigate to a page
        print("Navigating to example.com...\n")
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # 5. Begin a verification step
        runtime.begin_step("Verify page loaded correctly")

        # 6. Take a snapshot (required for element assertions)
        snapshot = runtime.snapshot()
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

    except Exception as e:
        print(f"\nError during execution: {e}")
        raise

    finally:
        # Close tracer and browser
        print("\nClosing tracer...")
        tracer.close(blocking=True)
        print(f"Trace saved to: ~/.sentience/traces/{run_id}.jsonl")

        browser.close()
        print("Done!")


if __name__ == "__main__":
    main()
