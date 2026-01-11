"""
Example: Agent Runtime with browser-use Integration

Demonstrates how to use AgentRuntime with browser-use library via BrowserBackendV0 protocol.
This pattern enables framework-agnostic browser integration for agent verification loops.

Key features:
- BrowserUseAdapter: Wraps browser-use BrowserSession into CDPBackendV0
- BrowserBackendV0 protocol: Minimal interface for browser operations
- Direct AgentRuntime construction: No need for from_sentience_browser factory

Requirements:
- browser-use library: pip install browser-use
- SENTIENCE_API_KEY (optional) - enables Pro tier Gateway refinement

Usage:
    python examples/agent_runtime_browser_use.py
"""

import asyncio
import os

from sentience import get_extension_dir
from sentience.agent_runtime import AgentRuntime
from sentience.backends import BrowserUseAdapter
from sentience.tracing import JsonlTraceSink, Tracer
from sentience.verification import (
    all_of,
    exists,
    not_exists,
    url_contains,
    url_matches,
)

# browser-use imports (requires: pip install browser-use)
try:
    from browser_use import BrowserProfile, BrowserSession
except ImportError:
    print("Error: browser-use library not installed.")
    print("Install with: pip install browser-use")
    exit(1)


async def main():
    # Get API key from environment (optional - enables Pro tier features)
    sentience_key = os.environ.get("SENTIENCE_API_KEY")

    print("Starting Agent Runtime with browser-use Integration Demo\n")

    # 1. Create tracer for verification event emission
    run_id = "browser-use-demo"
    sink = JsonlTraceSink(f"traces/{run_id}.jsonl")
    tracer = Tracer(run_id=run_id, sink=sink)
    print(f"Run ID: {run_id}\n")

    # 2. Create browser-use session with Sentience extension loaded
    # The extension is required for snapshot() to work
    extension_dir = get_extension_dir()
    profile = BrowserProfile(
        args=[f"--load-extension={extension_dir}"],
        headless=False,
    )
    session = BrowserSession(browser_profile=profile)
    await session.start()

    try:
        # 3. Create BrowserBackendV0 using BrowserUseAdapter
        # This wraps the browser-use session into the standard backend protocol
        adapter = BrowserUseAdapter(session)
        backend = await adapter.create_backend()
        print("Created CDPBackendV0 from browser-use session\n")

        # 4. Create AgentRuntime directly with backend
        # For Pro tier, pass sentience_api_key for Gateway element refinement
        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            sentience_api_key=sentience_key,  # Optional: enables Pro tier
        )

        # 5. Navigate using browser-use
        page = await session.get_current_page()
        print("Navigating to example.com...\n")
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")

        # 6. Begin a verification step
        runtime.begin_step("Verify page loaded correctly")

        # 7. Take a snapshot (uses Sentience extension via backend.eval())
        snapshot = await runtime.snapshot()
        print(f"Snapshot taken: {len(snapshot.elements)} elements found\n")

        # 8. Run assertions against current state
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

        # 9. Check if task is done (required assertion)
        task_complete = runtime.assert_done(
            exists("text~'Example Domain'"),
            "reached_example_page",
        )
        print(f"\n  [{'DONE' if task_complete else 'NOT DONE'}] reached_example_page")

        # 10. Get accumulated assertions for step_end event
        assertions_data = runtime.get_assertions_for_step_end()
        print(f"\nTotal assertions: {len(assertions_data['assertions'])}")
        print(f"Task done: {assertions_data.get('task_done', False)}")

        # 11. Check overall status
        print("\nVerification Summary:")
        print(f"  All passed: {runtime.all_assertions_passed()}")
        print(f"  Required passed: {runtime.required_assertions_passed()}")
        print(f"  Task complete: {runtime.is_task_done}")

    finally:
        # Close browser-use session
        await session.close()

        # Close tracer
        print("\nClosing tracer...")
        tracer.close()
        print(f"Trace saved to: traces/{run_id}.jsonl")
        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
