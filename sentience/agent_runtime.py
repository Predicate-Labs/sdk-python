"""
Agent runtime for verification loop support.

This module provides a thin runtime wrapper that combines:
1. Browser session management (via BrowserBackend protocol)
2. Snapshot/query helpers
3. Tracer for event emission
4. Assertion/verification methods

The AgentRuntime is designed to be used in agent verification loops where
you need to repeatedly take snapshots, execute actions, and verify results.

Example usage with browser-use:
    from browser_use import BrowserSession, BrowserProfile
    from sentience import get_extension_dir
    from sentience.backends import BrowserUseAdapter
    from sentience.agent_runtime import AgentRuntime
    from sentience.verification import url_matches, exists
    from sentience.tracing import Tracer, JsonlTraceSink

    # Setup browser-use with Sentience extension
    profile = BrowserProfile(args=[f"--load-extension={get_extension_dir()}"])
    session = BrowserSession(browser_profile=profile)
    await session.start()

    # Create adapter and backend
    adapter = BrowserUseAdapter(session)
    backend = await adapter.create_backend()

    # Navigate using browser-use
    page = await session.get_current_page()
    await page.goto("https://example.com")

    # Create runtime with backend
    sink = JsonlTraceSink("trace.jsonl")
    tracer = Tracer(run_id="test-run", sink=sink)
    runtime = AgentRuntime(backend=backend, tracer=tracer)

    # Take snapshot and run assertions
    await runtime.snapshot()
    runtime.assert_(url_matches(r"example\\.com"), label="on_homepage")
    runtime.assert_(exists("role=button"), label="has_buttons")

    # Check if task is done
    if runtime.assert_done(exists("text~'Success'"), label="task_complete"):
        print("Task completed!")

Example usage with AsyncSentienceBrowser (backward compatible):
    from sentience import AsyncSentienceBrowser
    from sentience.agent_runtime import AgentRuntime

    async with AsyncSentienceBrowser() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")

        runtime = await AgentRuntime.from_sentience_browser(
            browser=browser,
            page=page,
            tracer=tracer,
        )
        await runtime.snapshot()
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from .models import Snapshot, SnapshotOptions
from .verification import AssertContext, Predicate

if TYPE_CHECKING:
    from playwright.async_api import Page

    from .backends.protocol import BrowserBackend
    from .browser import AsyncSentienceBrowser
    from .tracing import Tracer


class AgentRuntime:
    """
    Runtime wrapper for agent verification loops.

    Provides ergonomic methods for:
    - snapshot(): Take page snapshot
    - assert_(): Evaluate assertion predicates
    - assert_done(): Assert task completion (required assertion)

    The runtime manages assertion state per step and emits verification events
    to the tracer for Studio timeline display.

    Attributes:
        backend: BrowserBackend instance for browser operations
        tracer: Tracer for event emission
        step_id: Current step identifier
        step_index: Current step index (0-based)
        last_snapshot: Most recent snapshot (for assertion context)
    """

    def __init__(
        self,
        backend: BrowserBackend,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
    ):
        """
        Initialize agent runtime with any BrowserBackend-compatible browser.

        Args:
            backend: Any browser implementing BrowserBackend protocol.
                     Examples:
                     - CDPBackendV0 (for browser-use via BrowserUseAdapter)
                     - PlaywrightBackend (future, for direct Playwright)
            tracer: Tracer for emitting verification events
            snapshot_options: Default options for snapshots
            sentience_api_key: API key for Pro/Enterprise tier (enables Gateway refinement)
        """
        self.backend = backend
        self.tracer = tracer

        # Build default snapshot options with API key if provided
        default_opts = snapshot_options or SnapshotOptions()
        if sentience_api_key:
            default_opts.sentience_api_key = sentience_api_key
            if default_opts.use_api is None:
                default_opts.use_api = True
        self._snapshot_options = default_opts

        # Step tracking
        self.step_id: str | None = None
        self.step_index: int = 0

        # Snapshot state
        self.last_snapshot: Snapshot | None = None

        # Cached URL (updated on snapshot or explicit get_url call)
        self._cached_url: str | None = None

        # Assertions accumulated during current step
        self._assertions_this_step: list[dict[str, Any]] = []

        # Task completion tracking
        self._task_done: bool = False
        self._task_done_label: str | None = None

    @classmethod
    async def from_sentience_browser(
        cls,
        browser: AsyncSentienceBrowser,
        page: Page,
        tracer: Tracer,
        snapshot_options: SnapshotOptions | None = None,
        sentience_api_key: str | None = None,
    ) -> AgentRuntime:
        """
        Create AgentRuntime from AsyncSentienceBrowser (backward compatibility).

        This factory method wraps an AsyncSentienceBrowser + Page combination
        into the new BrowserBackend-based AgentRuntime.

        Args:
            browser: AsyncSentienceBrowser instance
            page: Playwright Page for browser interaction
            tracer: Tracer for emitting verification events
            snapshot_options: Default options for snapshots
            sentience_api_key: API key for Pro/Enterprise tier

        Returns:
            AgentRuntime instance
        """
        from .backends.playwright_backend import PlaywrightBackend

        backend = PlaywrightBackend(page)
        runtime = cls(
            backend=backend,
            tracer=tracer,
            snapshot_options=snapshot_options,
            sentience_api_key=sentience_api_key,
        )
        # Store browser reference for snapshot() to use
        runtime._legacy_browser = browser
        runtime._legacy_page = page
        return runtime

    def _ctx(self) -> AssertContext:
        """
        Build assertion context from current state.

        Returns:
            AssertContext with current snapshot and URL
        """
        url = None
        if self.last_snapshot is not None:
            url = self.last_snapshot.url
        elif self._cached_url:
            url = self._cached_url

        return AssertContext(
            snapshot=self.last_snapshot,
            url=url,
            step_id=self.step_id,
        )

    async def get_url(self) -> str:
        """
        Get current page URL.

        Returns:
            Current page URL
        """
        url = await self.backend.get_url()
        self._cached_url = url
        return url

    async def snapshot(self, **kwargs: Any) -> Snapshot:
        """
        Take a snapshot of the current page state.

        This updates last_snapshot which is used as context for assertions.

        Args:
            **kwargs: Override default snapshot options for this call.
                     Common options:
                     - limit: Maximum elements to return
                     - goal: Task goal for ordinal support
                     - screenshot: Include screenshot
                     - show_overlay: Show visual overlay

        Returns:
            Snapshot of current page state
        """
        # Check if using legacy browser (backward compat)
        if hasattr(self, "_legacy_browser") and hasattr(self, "_legacy_page"):
            self.last_snapshot = await self._legacy_browser.snapshot(self._legacy_page, **kwargs)
            return self.last_snapshot

        # Use backend-agnostic snapshot
        from .backends.snapshot import snapshot as backend_snapshot

        # Merge default options with call-specific kwargs
        options_dict = self._snapshot_options.model_dump(exclude_none=True)
        options_dict.update(kwargs)
        options = SnapshotOptions(**options_dict)

        self.last_snapshot = await backend_snapshot(self.backend, options=options)
        return self.last_snapshot

    def begin_step(self, goal: str, step_index: int | None = None) -> str:
        """
        Begin a new step in the verification loop.

        This:
        - Generates a new step_id
        - Clears assertions from previous step
        - Increments step_index (or uses provided value)

        Args:
            goal: Description of what this step aims to achieve
            step_index: Optional explicit step index (otherwise auto-increments)

        Returns:
            Generated step_id
        """
        # Clear previous step state
        self._assertions_this_step = []

        # Generate new step_id
        self.step_id = str(uuid.uuid4())

        # Update step index
        if step_index is not None:
            self.step_index = step_index
        else:
            self.step_index += 1

        return self.step_id

    def assert_(
        self,
        predicate: Predicate,
        label: str,
        required: bool = False,
    ) -> bool:
        """
        Evaluate an assertion against current snapshot state.

        The assertion result is:
        1. Accumulated for inclusion in step_end.data.verify.signals.assertions
        2. Emitted as a dedicated 'verification' event for Studio timeline

        Args:
            predicate: Predicate function to evaluate
            label: Human-readable label for this assertion
            required: If True, this assertion gates step success (default: False)

        Returns:
            True if assertion passed, False otherwise
        """
        outcome = predicate(self._ctx())

        record = {
            "label": label,
            "passed": outcome.passed,
            "required": required,
            "reason": outcome.reason,
            "details": outcome.details,
        }
        self._assertions_this_step.append(record)

        # Emit dedicated verification event (Option B from design doc)
        # This makes assertions visible in Studio timeline
        self.tracer.emit(
            "verification",
            data={
                "kind": "assert",
                "passed": outcome.passed,
                **record,
            },
            step_id=self.step_id,
        )

        return outcome.passed

    def assert_done(
        self,
        predicate: Predicate,
        label: str,
    ) -> bool:
        """
        Assert task completion (required assertion).

        This is a convenience wrapper for assert_() with required=True.
        When the assertion passes, it marks the task as done.

        Use this for final verification that the agent's goal is complete.

        Args:
            predicate: Predicate function to evaluate
            label: Human-readable label for this assertion

        Returns:
            True if task is complete (assertion passed), False otherwise
        """
        ok = self.assert_(predicate, label=label, required=True)
        if ok:
            self._task_done = True
            self._task_done_label = label

            # Emit task_done verification event
            self.tracer.emit(
                "verification",
                data={
                    "kind": "task_done",
                    "passed": True,
                    "label": label,
                },
                step_id=self.step_id,
            )

        return ok

    def get_assertions_for_step_end(self) -> dict[str, Any]:
        """
        Get assertions data for inclusion in step_end.data.verify.signals.

        This is called when building the step_end event to include
        assertion results in the trace.

        Returns:
            Dictionary with 'assertions', 'task_done', 'task_done_label' keys
        """
        result: dict[str, Any] = {
            "assertions": self._assertions_this_step.copy(),
        }

        if self._task_done:
            result["task_done"] = True
            result["task_done_label"] = self._task_done_label

        return result

    def flush_assertions(self) -> list[dict[str, Any]]:
        """
        Get and clear assertions for current step.

        Call this at step end to get accumulated assertions
        for the step_end event, then clear for next step.

        Returns:
            List of assertion records from this step
        """
        assertions = self._assertions_this_step.copy()
        self._assertions_this_step = []
        return assertions

    @property
    def is_task_done(self) -> bool:
        """Check if task has been marked as done via assert_done()."""
        return self._task_done

    def reset_task_done(self) -> None:
        """Reset task_done state (for multi-task runs)."""
        self._task_done = False
        self._task_done_label = None

    def all_assertions_passed(self) -> bool:
        """
        Check if all assertions in current step passed.

        Returns:
            True if all assertions passed (or no assertions made)
        """
        return all(a["passed"] for a in self._assertions_this_step)

    def required_assertions_passed(self) -> bool:
        """
        Check if all required assertions in current step passed.

        Returns:
            True if all required assertions passed (or no required assertions)
        """
        required = [a for a in self._assertions_this_step if a.get("required")]
        return all(a["passed"] for a in required)
