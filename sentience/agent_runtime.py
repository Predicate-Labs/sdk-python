"""
Agent runtime for verification loop support.

This module provides a thin runtime wrapper that combines:
1. Browser session management
2. Snapshot/query helpers
3. Tracer for event emission
4. Assertion/verification methods

The AgentRuntime is designed to be used in agent verification loops where
you need to repeatedly take snapshots, execute actions, and verify results.

Example usage:
    from sentience import AsyncSentienceBrowser
    from sentience.agent_runtime import AgentRuntime
    from sentience.verification import url_matches, exists
    from sentience.tracing import Tracer, JsonlTraceSink

    async with AsyncSentienceBrowser() as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")

        sink = JsonlTraceSink("trace.jsonl")
        tracer = Tracer(run_id="test-run", sink=sink)

        runtime = AgentRuntime(browser=browser, page=page, tracer=tracer)

        # Take snapshot and run assertions
        await runtime.snapshot()
        runtime.assert_(url_matches(r"example\\.com"), label="on_homepage")
        runtime.assert_(exists("role=button"), label="has_buttons")

        # Check if task is done
        if runtime.assert_done(exists("text~'Success'"), label="task_complete"):
            print("Task completed!")
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from .verification import AssertContext, AssertOutcome, Predicate

if TYPE_CHECKING:
    from playwright.async_api import Page

    from .browser import AsyncSentienceBrowser
    from .models import Snapshot
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
        browser: AsyncSentienceBrowser instance
        page: Playwright Page instance
        tracer: Tracer for event emission
        step_id: Current step identifier
        step_index: Current step index (0-based)
        last_snapshot: Most recent snapshot (for assertion context)
    """

    def __init__(
        self,
        browser: AsyncSentienceBrowser,
        page: Page,
        tracer: Tracer,
    ):
        """
        Initialize agent runtime.

        Args:
            browser: AsyncSentienceBrowser instance for taking snapshots
            page: Playwright Page for browser interaction
            tracer: Tracer for emitting verification events
        """
        self.browser = browser
        self.page = page
        self.tracer = tracer

        # Step tracking
        self.step_id: str | None = None
        self.step_index: int = 0

        # Snapshot state
        self.last_snapshot: Snapshot | None = None

        # Assertions accumulated during current step
        self._assertions_this_step: list[dict[str, Any]] = []

        # Task completion tracking
        self._task_done: bool = False
        self._task_done_label: str | None = None

    def _ctx(self) -> AssertContext:
        """
        Build assertion context from current state.

        Returns:
            AssertContext with current snapshot and URL
        """
        url = None
        if self.last_snapshot is not None:
            url = self.last_snapshot.url
        elif self.page:
            url = self.page.url

        return AssertContext(
            snapshot=self.last_snapshot,
            url=url,
            step_id=self.step_id,
        )

    async def snapshot(self, **kwargs) -> Snapshot:
        """
        Take a snapshot of the current page state.

        This updates last_snapshot which is used as context for assertions.

        Args:
            **kwargs: Passed through to browser.snapshot()

        Returns:
            Snapshot of current page state
        """
        self.last_snapshot = await self.browser.snapshot(self.page, **kwargs)
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
        ok = self.assertTrue(predicate, label=label, required=True)

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
