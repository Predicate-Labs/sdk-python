"""
Sentience Agent: High-level automation agent using LLM + SDK
Implements observe-think-act loop for natural language commands
"""

import asyncio
import hashlib
import inspect
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional, Union

from .action_executor import ActionExecutor
from .agent_config import AgentConfig
from .base_agent import BaseAgent, BaseAgentAsync
from .browser import AsyncSentienceBrowser, SentienceBrowser
from .element_filter import ElementFilter
from .llm_interaction_handler import LLMInteractionHandler
from .llm_provider import LLMProvider, LLMResponse
from .models import (
    ActionHistory,
    ActionTokenUsage,
    AgentActionResult,
    Element,
    ScreenshotConfig,
    Snapshot,
    SnapshotOptions,
    StepHookContext,
    TokenStats,
)
from .protocols import AsyncBrowserProtocol, BrowserProtocol
from .snapshot import snapshot, snapshot_async
from .snapshot_diff import SnapshotDiff
from .trace_event_builder import TraceEventBuilder

if TYPE_CHECKING:
    from .tracing import Tracer


def _safe_tracer_call(
    tracer: Optional["Tracer"], method_name: str, verbose: bool, *args, **kwargs
) -> None:
    """
    Safely call tracer method, catching and logging errors without breaking execution.

    Args:
        tracer: Tracer instance or None
        method_name: Name of tracer method to call (e.g., "emit", "emit_error")
        verbose: Whether to print error messages
        *args: Positional arguments for the tracer method
        **kwargs: Keyword arguments for the tracer method
    """
    if not tracer:
        return
    try:
        method = getattr(tracer, method_name)
        if args and kwargs:
            method(*args, **kwargs)
        elif args:
            method(*args)
        elif kwargs:
            method(**kwargs)
        else:
            method()
    except Exception as tracer_error:
        # Tracer errors should not break agent execution
        if verbose:
            print(f"⚠️  Tracer error (non-fatal): {tracer_error}")


def _safe_hook_call_sync(
    hook: Callable[[StepHookContext], Any] | None,
    ctx: StepHookContext,
    verbose: bool,
) -> None:
    if not hook:
        return
    try:
        result = hook(ctx)
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(result)
            else:
                loop.create_task(result)
    except Exception as hook_error:
        if verbose:
            print(f"⚠️  Hook error (non-fatal): {hook_error}")
        else:
            logging.getLogger(__name__).warning("Hook error (non-fatal): %s", hook_error)


async def _safe_hook_call_async(
    hook: Callable[[StepHookContext], Any] | None,
    ctx: StepHookContext,
    verbose: bool,
) -> None:
    if not hook:
        return
    try:
        result = hook(ctx)
        if inspect.isawaitable(result):
            await result
    except Exception as hook_error:
        if verbose:
            print(f"⚠️  Hook error (non-fatal): {hook_error}")
        else:
            logging.getLogger(__name__).warning("Hook error (non-fatal): %s", hook_error)


class SentienceAgent(BaseAgent):
    """
    High-level agent that combines Sentience SDK with any LLM provider.

    Uses observe-think-act loop to execute natural language commands:
    1. OBSERVE: Get snapshot of current page state
    2. THINK: Query LLM to decide next action
    3. ACT: Execute action using SDK

    Example:
        >>> from sentience import SentienceBrowser, SentienceAgent
        >>> from sentience.llm_provider import OpenAIProvider
        >>>
        >>> browser = SentienceBrowser(api_key="sentience_key")
        >>> llm = OpenAIProvider(api_key="openai_key", model="gpt-4o")
        >>> agent = SentienceAgent(browser, llm)
        >>>
        >>> with browser:
        >>>     browser.page.goto("https://google.com")
        >>>     agent.act("Click the search box")
        >>>     agent.act("Type 'magic mouse' into the search field")
        >>>     agent.act("Press Enter key")
    """

    def __init__(
        self,
        browser: SentienceBrowser | BrowserProtocol,
        llm: LLMProvider,
        default_snapshot_limit: int = 50,
        verbose: bool = True,
        tracer: Optional["Tracer"] = None,
        config: Optional["AgentConfig"] = None,
    ):
        """
        Initialize Sentience Agent

        Args:
            browser: SentienceBrowser instance or BrowserProtocol-compatible object
                    (for testing, can use mock objects that implement BrowserProtocol)
            llm: LLM provider (OpenAIProvider, AnthropicProvider, etc.)
            default_snapshot_limit: Default maximum elements to include in context (default: 50)
            verbose: Print execution logs (default: True)
            tracer: Optional Tracer instance for execution tracking (default: None)
            config: Optional AgentConfig for advanced configuration (default: None)
        """
        self.browser = browser
        self.llm = llm
        self.default_snapshot_limit = default_snapshot_limit
        self.verbose = verbose
        self.tracer = tracer
        self.config = config or AgentConfig()

        # Initialize handlers
        self.llm_handler = LLMInteractionHandler(llm)
        self.action_executor = ActionExecutor(browser)

        # Screenshot sequence counter
        # Execution history
        self.history: list[dict[str, Any]] = []

        # Token usage tracking (will be converted to TokenStats on get_token_stats())
        self._token_usage_raw = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "by_action": [],
        }

        # Step counter for tracing
        self._step_count = 0

        # Previous snapshot for diff detection
        self._previous_snapshot: Snapshot | None = None

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _best_effort_post_snapshot_digest(self, goal: str) -> str | None:
        """
        Best-effort post-action snapshot digest for tracing (async).
        """
        try:
            snap_opts = SnapshotOptions(
                limit=min(10, self.default_snapshot_limit),
                goal=f"{goal} (post)",
            )
            snap_opts.screenshot = False
            snap_opts.show_overlay = self.config.show_overlay if self.config else None
            post_snap = await snapshot_async(self.browser, snap_opts)
            if post_snap.status != "success":
                return None
            digest_input = f"{post_snap.url}{post_snap.timestamp}"
            return f"sha256:{self._compute_hash(digest_input)}"
        except Exception:
            return None

    def _best_effort_post_snapshot_digest(self, goal: str) -> str | None:
        """
        Best-effort post-action snapshot digest for tracing.
        """
        try:
            snap_opts = SnapshotOptions(
                limit=min(10, self.default_snapshot_limit),
                goal=f"{goal} (post)",
            )
            snap_opts.screenshot = False
            snap_opts.show_overlay = self.config.show_overlay if self.config else None
            post_snap = snapshot(self.browser, snap_opts)
            if post_snap.status != "success":
                return None
            digest_input = f"{post_snap.url}{post_snap.timestamp}"
            return f"sha256:{self._compute_hash(digest_input)}"
        except Exception:
            return None

    def _get_element_bbox(self, element_id: int | None, snap: Snapshot) -> dict[str, float] | None:
        """Get bounding box for an element from snapshot."""
        if element_id is None:
            return None
        for el in snap.elements:
            if el.id == element_id:
                return {
                    "x": el.bbox.x,
                    "y": el.bbox.y,
                    "width": el.bbox.width,
                    "height": el.bbox.height,
                }
        return None

    def act(  # noqa: C901
        self,
        goal: str,
        max_retries: int = 2,
        snapshot_options: SnapshotOptions | None = None,
        on_step_start: Callable[[StepHookContext], Any] | None = None,
        on_step_end: Callable[[StepHookContext], Any] | None = None,
    ) -> AgentActionResult:
        """
        Execute a high-level goal using observe → think → act loop

        Args:
            goal: Natural language instruction (e.g., "Click the Sign In button")
            max_retries: Number of retries on failure (default: 2)
            snapshot_options: Optional SnapshotOptions for this specific action

        Returns:
            AgentActionResult with execution details

        Example:
            >>> result = agent.act("Click the search box")
            >>> print(result.success, result.action, result.element_id)
            True click 42
            >>> # Backward compatible dict access
            >>> print(result["element_id"])  # Works but shows deprecation warning
            42
        """
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"🤖 Agent Goal: {goal}")
            print(f"{'=' * 70}")

        # Generate step ID for tracing
        self._step_count += 1
        step_id = f"step-{self._step_count}"

        pre_url = self.browser.page.url if self.browser.page else None
        # Emit step_start trace event if tracer is enabled
        if self.tracer:
            _safe_tracer_call(
                self.tracer,
                "emit_step_start",
                self.verbose,
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                pre_url=pre_url,
            )

        _safe_hook_call_sync(
            on_step_start,
            StepHookContext(
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                url=pre_url,
            ),
            self.verbose,
        )

        # Track data collected during step execution for step_end emission on failure
        _step_snap_with_diff: Snapshot | None = None
        _step_pre_url: str | None = None
        _step_llm_response: LLMResponse | None = None
        _step_result: AgentActionResult | None = None
        _step_duration_ms: int = 0

        for attempt in range(max_retries + 1):
            try:
                # 1. OBSERVE: Get refined semantic snapshot
                start_time = time.time()

                # Use provided options or create default
                snap_opts = snapshot_options or SnapshotOptions(limit=self.default_snapshot_limit)
                # Only set goal if not already provided
                if snap_opts.goal is None:
                    snap_opts.goal = goal

                # Apply AgentConfig screenshot settings if not overridden by snapshot_options
                if snapshot_options is None and self.config:
                    if self.config.capture_screenshots:
                        # Create ScreenshotConfig from AgentConfig
                        snap_opts.screenshot = ScreenshotConfig(
                            format=self.config.screenshot_format,
                            quality=(
                                self.config.screenshot_quality
                                if self.config.screenshot_format == "jpeg"
                                else None
                            ),
                        )
                    else:
                        snap_opts.screenshot = False
                    # Apply show_overlay from AgentConfig
                    snap_opts.show_overlay = self.config.show_overlay

                # Call snapshot with options object (matches TypeScript API)
                snap = snapshot(self.browser, snap_opts)

                if snap.status != "success":
                    raise RuntimeError(f"Snapshot failed: {snap.error}")

                # Compute diff_status by comparing with previous snapshot
                elements_with_diff = SnapshotDiff.compute_diff_status(snap, self._previous_snapshot)

                # Create snapshot with diff_status populated
                snap_with_diff = Snapshot(
                    status=snap.status,
                    timestamp=snap.timestamp,
                    url=snap.url,
                    viewport=snap.viewport,
                    elements=elements_with_diff,
                    screenshot=snap.screenshot,
                    screenshot_format=snap.screenshot_format,
                    error=snap.error,
                )

                # Track for step_end emission on failure
                _step_snap_with_diff = snap_with_diff
                _step_pre_url = snap.url

                # Update previous snapshot for next comparison
                self._previous_snapshot = snap

                # Apply element filtering based on goal
                filtered_elements = self.filter_elements(snap_with_diff, goal)

                # Emit snapshot trace event if tracer is enabled
                if self.tracer:
                    # Build snapshot event data (use snap_with_diff to include diff_status)
                    snapshot_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)

                    # Always include screenshot in trace event for studio viewer compatibility
                    # CloudTraceSink will extract and upload screenshots separately, then remove
                    # screenshot_base64 from events before uploading the trace file.
                    if snap.screenshot:
                        # Extract base64 string from data URL if needed
                        if snap.screenshot.startswith("data:image"):
                            # Format: "data:image/jpeg;base64,{base64_string}"
                            screenshot_base64 = (
                                snap.screenshot.split(",", 1)[1]
                                if "," in snap.screenshot
                                else snap.screenshot
                            )
                        else:
                            screenshot_base64 = snap.screenshot

                        snapshot_data["screenshot_base64"] = screenshot_base64
                        if snap.screenshot_format:
                            snapshot_data["screenshot_format"] = snap.screenshot_format

                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "snapshot",
                        snapshot_data,
                        step_id=step_id,
                    )

                # Create filtered snapshot (use snap_with_diff to preserve metadata)
                filtered_snap = Snapshot(
                    status=snap_with_diff.status,
                    timestamp=snap_with_diff.timestamp,
                    url=snap_with_diff.url,
                    viewport=snap_with_diff.viewport,
                    elements=filtered_elements,
                    screenshot=snap_with_diff.screenshot,
                    screenshot_format=snap_with_diff.screenshot_format,
                    error=snap_with_diff.error,
                )

                # 2. GROUND: Format elements for LLM context
                context = self.llm_handler.build_context(filtered_snap, goal)

                # 3. THINK: Query LLM for next action
                llm_response = self.llm_handler.query_llm(context, goal)

                # Track for step_end emission on failure
                _step_llm_response = llm_response

                # Emit LLM query trace event if tracer is enabled
                if self.tracer:
                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "llm_query",
                        {
                            "prompt_tokens": llm_response.prompt_tokens,
                            "completion_tokens": llm_response.completion_tokens,
                            "model": llm_response.model_name,
                            "response": llm_response.content[:200],  # Truncate for brevity
                        },
                        step_id=step_id,
                    )

                if self.verbose:
                    print(f"🧠 LLM Decision: {llm_response.content}")

                # Track token usage
                self._track_tokens(goal, llm_response)

                # Parse action from LLM response
                action_str = self.llm_handler.extract_action(llm_response.content)

                # 4. EXECUTE: Parse and run action
                result_dict = self.action_executor.execute(action_str, filtered_snap)

                duration_ms = int((time.time() - start_time) * 1000)

                # Create AgentActionResult from execution result
                result = AgentActionResult(
                    success=result_dict["success"],
                    action=result_dict["action"],
                    goal=goal,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    element_id=result_dict.get("element_id"),
                    text=result_dict.get("text"),
                    key=result_dict.get("key"),
                    outcome=result_dict.get("outcome"),
                    url_changed=result_dict.get("url_changed"),
                    error=result_dict.get("error"),
                    message=result_dict.get("message"),
                    cursor=result_dict.get("cursor"),
                )

                # Track for step_end emission on failure
                _step_result = result
                _step_duration_ms = duration_ms

                # Emit action execution trace event if tracer is enabled
                post_url = self.browser.page.url if self.browser.page else None
                if self.tracer:

                    # Include element data for live overlay visualization
                    elements_data = [
                        {
                            "id": el.id,
                            "bbox": {
                                "x": el.bbox.x,
                                "y": el.bbox.y,
                                "width": el.bbox.width,
                                "height": el.bbox.height,
                            },
                            "role": el.role,
                            "text": el.text[:50] if el.text else "",
                        }
                        for el in filtered_snap.elements[:50]
                    ]

                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "action",
                        {
                            "action": result.action,
                            "element_id": result.element_id,
                            "success": result.success,
                            "outcome": result.outcome,
                            "duration_ms": duration_ms,
                            "post_url": post_url,
                            "elements": elements_data,  # Add element data for overlay
                            "target_element_id": result.element_id,  # Highlight target in red
                            "cursor": result.cursor,
                        },
                        step_id=step_id,
                    )

                # 5. RECORD: Track history
                self.history.append(
                    {
                        "goal": goal,
                        "action": action_str,
                        "result": result.model_dump(),  # Store as dict
                        "success": result.success,
                        "attempt": attempt,
                        "duration_ms": duration_ms,
                    }
                )

                if self.verbose:
                    status = "✅" if result.success else "❌"
                    print(f"{status} Completed in {duration_ms}ms")

                # Emit step completion trace event if tracer is enabled
                if self.tracer:
                    # Get pre_url from step_start (stored in tracer or use current)
                    pre_url = snap.url

                    # Compute snapshot digest (simplified - use URL + timestamp)
                    snapshot_digest = f"sha256:{self._compute_hash(f'{pre_url}{snap.timestamp}')}"

                    # Build LLM data
                    llm_response_text = llm_response.content
                    llm_response_hash = f"sha256:{self._compute_hash(llm_response_text)}"
                    llm_data = {
                        "response_text": llm_response_text,
                        "response_hash": llm_response_hash,
                        "usage": {
                            "prompt_tokens": llm_response.prompt_tokens or 0,
                            "completion_tokens": llm_response.completion_tokens or 0,
                            "total_tokens": llm_response.total_tokens or 0,
                        },
                    }

                    # Build exec data
                    exec_data = {
                        "success": result.success,
                        "action": result.action,
                        "outcome": result.outcome
                        or (
                            f"Action {result.action} executed successfully"
                            if result.success
                            else f"Action {result.action} failed"
                        ),
                        "duration_ms": duration_ms,
                    }
                    if result.cursor is not None:
                        exec_data["cursor"] = result.cursor

                    # Add optional exec fields
                    if result.element_id is not None:
                        exec_data["element_id"] = result.element_id
                        # Add bounding box if element found
                        bbox = self._get_element_bbox(result.element_id, snap)
                        if bbox:
                            exec_data["bounding_box"] = bbox
                    if result.text is not None:
                        exec_data["text"] = result.text
                    if result.key is not None:
                        exec_data["key"] = result.key
                    if result.error is not None:
                        exec_data["error"] = result.error

                    # Build verify data (simplified - based on success and url_changed)
                    verify_passed = result.success and (
                        result.url_changed or result.action != "click"
                    )
                    verify_signals = {
                        "url_changed": result.url_changed or False,
                    }
                    if result.error:
                        verify_signals["error"] = result.error

                    # Add elements_found array if element was targeted
                    if result.element_id is not None:
                        bbox = self._get_element_bbox(result.element_id, snap)
                        if bbox:
                            verify_signals["elements_found"] = [
                                {
                                    "label": f"Element {result.element_id}",
                                    "bounding_box": bbox,
                                }
                            ]

                    verify_data = {
                        "passed": verify_passed,
                        "signals": verify_signals,
                    }

                    # Build elements data for pre field (include diff_status from snap_with_diff)
                    # Use the same format as build_snapshot_event for consistency
                    snapshot_event_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)
                    pre_elements = snapshot_event_data.get("elements", [])

                    post_snapshot_digest = (
                        self._best_effort_post_snapshot_digest(goal) if self.tracer else None
                    )

                    # Build complete step_end event
                    step_end_data = TraceEventBuilder.build_step_end_event(
                        step_id=step_id,
                        step_index=self._step_count,
                        goal=goal,
                        attempt=attempt,
                        pre_url=pre_url,
                        post_url=post_url,
                        snapshot_digest=snapshot_digest,
                        post_snapshot_digest=post_snapshot_digest,
                        llm_data=llm_data,
                        exec_data=exec_data,
                        verify_data=verify_data,
                        pre_elements=pre_elements,
                    )

                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "step_end",
                        step_end_data,
                        step_id=step_id,
                    )

                _safe_hook_call_sync(
                    on_step_end,
                    StepHookContext(
                        step_id=step_id,
                        step_index=self._step_count,
                        goal=goal,
                        attempt=attempt,
                        url=post_url,
                        success=result.success,
                        outcome=result.outcome,
                        error=result.error,
                    ),
                    self.verbose,
                )
                return result

            except Exception as e:
                # Emit error trace event if tracer is enabled
                if self.tracer:
                    _safe_tracer_call(
                        self.tracer,
                        "emit_error",
                        self.verbose,
                        step_id=step_id,
                        error=str(e),
                        attempt=attempt,
                    )

                if attempt < max_retries:
                    if self.verbose:
                        print(f"⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                    time.sleep(1.0)  # Brief delay before retry
                    continue
                else:
                    # Emit step_end with whatever data we collected before failure
                    # This ensures diff_status and other fields are preserved in traces
                    if self.tracer and _step_snap_with_diff is not None:
                        post_url = self.browser.page.url if self.browser.page else None
                        snapshot_digest = f"sha256:{self._compute_hash(f'{_step_pre_url}{_step_snap_with_diff.timestamp}')}"

                        # Build pre_elements from snap_with_diff (includes diff_status)
                        snapshot_event_data = TraceEventBuilder.build_snapshot_event(
                            _step_snap_with_diff
                        )
                        pre_elements = snapshot_event_data.get("elements", [])

                        # Build LLM data if available
                        llm_data = None
                        if _step_llm_response:
                            llm_response_text = _step_llm_response.content
                            llm_response_hash = f"sha256:{self._compute_hash(llm_response_text)}"
                            llm_data = {
                                "response_text": llm_response_text,
                                "response_hash": llm_response_hash,
                                "usage": {
                                    "prompt_tokens": _step_llm_response.prompt_tokens or 0,
                                    "completion_tokens": _step_llm_response.completion_tokens or 0,
                                    "total_tokens": _step_llm_response.total_tokens or 0,
                                },
                            }

                        # Build exec data (failure state)
                        exec_data = {
                            "success": False,
                            "action": _step_result.action if _step_result else "error",
                            "outcome": str(e),
                            "duration_ms": _step_duration_ms,
                        }

                        # Build step_end event for failed step
                        step_end_data = TraceEventBuilder.build_step_end_event(
                            step_id=step_id,
                            step_index=self._step_count,
                            goal=goal,
                            attempt=attempt,
                            pre_url=_step_pre_url,
                            post_url=post_url,
                            snapshot_digest=snapshot_digest,
                            post_snapshot_digest=None,
                            llm_data=llm_data,
                            exec_data=exec_data,
                            verify_data=None,
                            pre_elements=pre_elements,
                        )

                        _safe_tracer_call(
                            self.tracer,
                            "emit",
                            self.verbose,
                            "step_end",
                            step_end_data,
                            step_id=step_id,
                        )

                    # Create error result
                    error_result = AgentActionResult(
                        success=False,
                        action="error",
                        goal=goal,
                        duration_ms=0,
                        attempt=attempt,
                        error=str(e),
                    )
                    self.history.append(
                        {
                            "goal": goal,
                            "action": "error",
                            "result": error_result.model_dump(),
                            "success": False,
                            "attempt": attempt,
                            "duration_ms": 0,
                        }
                    )
                    _safe_hook_call_sync(
                        on_step_end,
                        StepHookContext(
                            step_id=step_id,
                            step_index=self._step_count,
                            goal=goal,
                            attempt=attempt,
                            url=_step_pre_url,
                            success=False,
                            outcome="exception",
                            error=str(e),
                        ),
                        self.verbose,
                    )
                    raise RuntimeError(f"Failed after {max_retries} retries: {e}")

    def _track_tokens(self, goal: str, llm_response: LLMResponse):
        """
        Track token usage for analytics

        Args:
            goal: User goal
            llm_response: LLM response with token usage
        """
        if llm_response.prompt_tokens:
            self._token_usage_raw["total_prompt_tokens"] += llm_response.prompt_tokens
        if llm_response.completion_tokens:
            self._token_usage_raw["total_completion_tokens"] += llm_response.completion_tokens
        if llm_response.total_tokens:
            self._token_usage_raw["total_tokens"] += llm_response.total_tokens

        self._token_usage_raw["by_action"].append(
            {
                "goal": goal,
                "prompt_tokens": llm_response.prompt_tokens or 0,
                "completion_tokens": llm_response.completion_tokens or 0,
                "total_tokens": llm_response.total_tokens or 0,
                "model": llm_response.model_name,
            }
        )

    def get_token_stats(self) -> TokenStats:
        """
        Get token usage statistics

        Returns:
            TokenStats with token usage breakdown
        """
        by_action = [ActionTokenUsage(**action) for action in self._token_usage_raw["by_action"]]
        return TokenStats(
            total_prompt_tokens=self._token_usage_raw["total_prompt_tokens"],
            total_completion_tokens=self._token_usage_raw["total_completion_tokens"],
            total_tokens=self._token_usage_raw["total_tokens"],
            by_action=by_action,
        )

    def get_history(self) -> list[ActionHistory]:
        """
        Get execution history

        Returns:
            List of ActionHistory entries
        """
        return [ActionHistory(**h) for h in self.history]

    def clear_history(self) -> None:
        """Clear execution history and reset token counters"""
        self.history.clear()
        self._token_usage_raw = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "by_action": [],
        }

    def filter_elements(self, snapshot: Snapshot, goal: str | None = None) -> list[Element]:
        """
        Filter elements from snapshot based on goal context.

        This implementation uses ElementFilter to apply goal-based keyword matching
        to boost relevant elements and filters out irrelevant ones.

        Args:
            snapshot: Current page snapshot
            goal: User's goal (can inform filtering)

        Returns:
            Filtered list of elements
        """
        return ElementFilter.filter_by_goal(snapshot, goal, self.default_snapshot_limit)


class SentienceAgentAsync(BaseAgentAsync):
    """
    High-level async agent that combines Sentience SDK with any LLM provider.

    Uses observe-think-act loop to execute natural language commands:
    1. OBSERVE: Get snapshot of current page state
    2. THINK: Query LLM to decide next action
    3. ACT: Execute action using SDK

    Example:
        >>> from sentience.async_api import AsyncSentienceBrowser
        >>> from sentience.agent import SentienceAgentAsync
        >>> from sentience.llm_provider import OpenAIProvider
        >>>
        >>> async with AsyncSentienceBrowser() as browser:
        >>>     await browser.goto("https://google.com")
        >>>     llm = OpenAIProvider(api_key="openai_key", model="gpt-4o")
        >>>     agent = SentienceAgentAsync(browser, llm)
        >>>     await agent.act("Click the search box")
        >>>     await agent.act("Type 'magic mouse' into the search field")
        >>>     await agent.act("Press Enter key")
    """

    def __init__(
        self,
        browser: AsyncSentienceBrowser,
        llm: LLMProvider,
        default_snapshot_limit: int = 50,
        verbose: bool = True,
        tracer: Optional["Tracer"] = None,
        config: Optional["AgentConfig"] = None,
    ):
        """
        Initialize Sentience Agent (async)

        Args:
            browser: AsyncSentienceBrowser instance
            llm: LLM provider (OpenAIProvider, AnthropicProvider, etc.)
            default_snapshot_limit: Default maximum elements to include in context (default: 50)
            verbose: Print execution logs (default: True)
            tracer: Optional Tracer instance for execution tracking (default: None)
            config: Optional AgentConfig for advanced configuration (default: None)
        """
        self.browser = browser
        self.llm = llm
        self.default_snapshot_limit = default_snapshot_limit
        self.verbose = verbose
        self.tracer = tracer
        self.config = config or AgentConfig()

        # Initialize handlers
        self.llm_handler = LLMInteractionHandler(llm)
        self.action_executor = ActionExecutor(browser)

        # Screenshot sequence counter
        # Execution history
        self.history: list[dict[str, Any]] = []

        # Token usage tracking (will be converted to TokenStats on get_token_stats())
        self._token_usage_raw = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "by_action": [],
        }

        # Step counter for tracing
        self._step_count = 0

        # Previous snapshot for diff detection
        self._previous_snapshot: Snapshot | None = None

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _get_element_bbox(self, element_id: int | None, snap: Snapshot) -> dict[str, float] | None:
        """Get bounding box for an element from snapshot."""
        if element_id is None:
            return None
        for el in snap.elements:
            if el.id == element_id:
                return {
                    "x": el.bbox.x,
                    "y": el.bbox.y,
                    "width": el.bbox.width,
                    "height": el.bbox.height,
                }
        return None

    async def act(  # noqa: C901
        self,
        goal: str,
        max_retries: int = 2,
        snapshot_options: SnapshotOptions | None = None,
        on_step_start: Callable[[StepHookContext], Any] | None = None,
        on_step_end: Callable[[StepHookContext], Any] | None = None,
    ) -> AgentActionResult:
        """
        Execute a high-level goal using observe → think → act loop (async)

        Args:
            goal: Natural language instruction (e.g., "Click the Sign In button")
            max_retries: Number of retries on failure (default: 2)
            snapshot_options: Optional SnapshotOptions for this specific action

        Returns:
            AgentActionResult with execution details

        Example:
            >>> result = await agent.act("Click the search box")
            >>> print(result.success, result.action, result.element_id)
            True click 42
        """
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"🤖 Agent Goal: {goal}")
            print(f"{'=' * 70}")

        # Generate step ID for tracing
        self._step_count += 1
        step_id = f"step-{self._step_count}"

        pre_url = self.browser.page.url if self.browser.page else None
        # Emit step_start trace event if tracer is enabled
        if self.tracer:
            _safe_tracer_call(
                self.tracer,
                "emit_step_start",
                self.verbose,
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                pre_url=pre_url,
            )

        await _safe_hook_call_async(
            on_step_start,
            StepHookContext(
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                url=pre_url,
            ),
            self.verbose,
        )

        # Track data collected during step execution for step_end emission on failure
        _step_snap_with_diff: Snapshot | None = None
        _step_pre_url: str | None = None
        _step_llm_response: LLMResponse | None = None
        _step_result: AgentActionResult | None = None
        _step_duration_ms: int = 0

        for attempt in range(max_retries + 1):
            try:
                # 1. OBSERVE: Get refined semantic snapshot
                start_time = time.time()

                # Use provided options or create default
                snap_opts = snapshot_options or SnapshotOptions(limit=self.default_snapshot_limit)
                # Only set goal if not already provided
                if snap_opts.goal is None:
                    snap_opts.goal = goal

                # Apply AgentConfig screenshot settings if not overridden by snapshot_options
                # Only apply if snapshot_options wasn't provided OR if screenshot wasn't explicitly set
                # (snapshot_options.screenshot defaults to False, so we check if it's still False)
                if self.config and (snapshot_options is None or snap_opts.screenshot is False):
                    if self.config.capture_screenshots:
                        # Create ScreenshotConfig from AgentConfig
                        snap_opts.screenshot = ScreenshotConfig(
                            format=self.config.screenshot_format,
                            quality=(
                                self.config.screenshot_quality
                                if self.config.screenshot_format == "jpeg"
                                else None
                            ),
                        )
                    else:
                        snap_opts.screenshot = False
                    # Apply show_overlay from AgentConfig
                    # Note: User can override by explicitly passing show_overlay in snapshot_options
                    snap_opts.show_overlay = self.config.show_overlay

                # Call snapshot with options object (matches TypeScript API)
                snap = await snapshot_async(self.browser, snap_opts)

                if snap.status != "success":
                    raise RuntimeError(f"Snapshot failed: {snap.error}")

                # Compute diff_status by comparing with previous snapshot
                elements_with_diff = SnapshotDiff.compute_diff_status(snap, self._previous_snapshot)

                # Create snapshot with diff_status populated
                snap_with_diff = Snapshot(
                    status=snap.status,
                    timestamp=snap.timestamp,
                    url=snap.url,
                    viewport=snap.viewport,
                    elements=elements_with_diff,
                    screenshot=snap.screenshot,
                    screenshot_format=snap.screenshot_format,
                    error=snap.error,
                )

                # Track for step_end emission on failure
                _step_snap_with_diff = snap_with_diff
                _step_pre_url = snap.url

                # Update previous snapshot for next comparison
                self._previous_snapshot = snap

                # Apply element filtering based on goal
                filtered_elements = self.filter_elements(snap_with_diff, goal)

                # Emit snapshot trace event if tracer is enabled
                if self.tracer:
                    # Build snapshot event data (use snap_with_diff to include diff_status)
                    snapshot_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)

                    # Always include screenshot in trace event for studio viewer compatibility
                    # CloudTraceSink will extract and upload screenshots separately, then remove
                    # screenshot_base64 from events before uploading the trace file.
                    if snap.screenshot:
                        # Extract base64 string from data URL if needed
                        if snap.screenshot.startswith("data:image"):
                            # Format: "data:image/jpeg;base64,{base64_string}"
                            screenshot_base64 = (
                                snap.screenshot.split(",", 1)[1]
                                if "," in snap.screenshot
                                else snap.screenshot
                            )
                        else:
                            screenshot_base64 = snap.screenshot

                        snapshot_data["screenshot_base64"] = screenshot_base64
                        if snap.screenshot_format:
                            snapshot_data["screenshot_format"] = snap.screenshot_format

                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "snapshot",
                        snapshot_data,
                        step_id=step_id,
                    )

                # Create filtered snapshot (use snap_with_diff to preserve metadata)
                filtered_snap = Snapshot(
                    status=snap_with_diff.status,
                    timestamp=snap_with_diff.timestamp,
                    url=snap_with_diff.url,
                    viewport=snap_with_diff.viewport,
                    elements=filtered_elements,
                    screenshot=snap_with_diff.screenshot,
                    screenshot_format=snap_with_diff.screenshot_format,
                    error=snap_with_diff.error,
                )

                # 2. GROUND: Format elements for LLM context
                context = self.llm_handler.build_context(filtered_snap, goal)

                # 3. THINK: Query LLM for next action
                llm_response = self.llm_handler.query_llm(context, goal)

                # Track for step_end emission on failure
                _step_llm_response = llm_response

                # Emit LLM query trace event if tracer is enabled
                if self.tracer:
                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "llm_query",
                        {
                            "prompt_tokens": llm_response.prompt_tokens,
                            "completion_tokens": llm_response.completion_tokens,
                            "model": llm_response.model_name,
                            "response": llm_response.content[:200],  # Truncate for brevity
                        },
                        step_id=step_id,
                    )

                if self.verbose:
                    print(f"🧠 LLM Decision: {llm_response.content}")

                # Track token usage
                self._track_tokens(goal, llm_response)

                # Parse action from LLM response
                action_str = self.llm_handler.extract_action(llm_response.content)

                # 4. EXECUTE: Parse and run action
                result_dict = await self.action_executor.execute_async(action_str, filtered_snap)

                duration_ms = int((time.time() - start_time) * 1000)

                # Create AgentActionResult from execution result
                result = AgentActionResult(
                    success=result_dict["success"],
                    action=result_dict["action"],
                    goal=goal,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    element_id=result_dict.get("element_id"),
                    text=result_dict.get("text"),
                    key=result_dict.get("key"),
                    outcome=result_dict.get("outcome"),
                    url_changed=result_dict.get("url_changed"),
                    error=result_dict.get("error"),
                    message=result_dict.get("message"),
                )

                # Track for step_end emission on failure
                _step_result = result
                _step_duration_ms = duration_ms

                # Emit action execution trace event if tracer is enabled
                if self.tracer:
                    post_url = self.browser.page.url if self.browser.page else None

                    # Include element data for live overlay visualization
                    elements_data = [
                        {
                            "id": el.id,
                            "bbox": {
                                "x": el.bbox.x,
                                "y": el.bbox.y,
                                "width": el.bbox.width,
                                "height": el.bbox.height,
                            },
                            "role": el.role,
                            "text": el.text[:50] if el.text else "",
                        }
                        for el in filtered_snap.elements[:50]
                    ]

                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "action",
                        {
                            "action": result.action,
                            "element_id": result.element_id,
                            "success": result.success,
                            "outcome": result.outcome,
                            "duration_ms": duration_ms,
                            "post_url": post_url,
                            "elements": elements_data,  # Add element data for overlay
                            "target_element_id": result.element_id,  # Highlight target in red
                        },
                        step_id=step_id,
                    )

                # 5. RECORD: Track history
                self.history.append(
                    {
                        "goal": goal,
                        "action": action_str,
                        "result": result.model_dump(),  # Store as dict
                        "success": result.success,
                        "attempt": attempt,
                        "duration_ms": duration_ms,
                    }
                )

                if self.verbose:
                    status = "✅" if result.success else "❌"
                    print(f"{status} Completed in {duration_ms}ms")

                # Emit step completion trace event if tracer is enabled
                if self.tracer:
                    # Get pre_url from step_start (stored in tracer or use current)
                    pre_url = snap.url
                    post_url = self.browser.page.url if self.browser.page else None

                    # Compute snapshot digest (simplified - use URL + timestamp)
                    snapshot_digest = f"sha256:{self._compute_hash(f'{pre_url}{snap.timestamp}')}"

                    # Build LLM data
                    llm_response_text = llm_response.content
                    llm_response_hash = f"sha256:{self._compute_hash(llm_response_text)}"
                    llm_data = {
                        "response_text": llm_response_text,
                        "response_hash": llm_response_hash,
                        "usage": {
                            "prompt_tokens": llm_response.prompt_tokens or 0,
                            "completion_tokens": llm_response.completion_tokens or 0,
                            "total_tokens": llm_response.total_tokens or 0,
                        },
                    }

                    # Build exec data
                    exec_data = {
                        "success": result.success,
                        "action": result.action,
                        "outcome": result.outcome
                        or (
                            f"Action {result.action} executed successfully"
                            if result.success
                            else f"Action {result.action} failed"
                        ),
                        "duration_ms": duration_ms,
                    }

                    # Add optional exec fields
                    if result.element_id is not None:
                        exec_data["element_id"] = result.element_id
                        # Add bounding box if element found
                        bbox = self._get_element_bbox(result.element_id, snap)
                        if bbox:
                            exec_data["bounding_box"] = bbox
                    if result.text is not None:
                        exec_data["text"] = result.text
                    if result.key is not None:
                        exec_data["key"] = result.key
                    if result.error is not None:
                        exec_data["error"] = result.error

                    # Build verify data (simplified - based on success and url_changed)
                    verify_passed = result.success and (
                        result.url_changed or result.action != "click"
                    )
                    verify_signals = {
                        "url_changed": result.url_changed or False,
                    }
                    if result.error:
                        verify_signals["error"] = result.error

                    # Add elements_found array if element was targeted
                    if result.element_id is not None:
                        bbox = self._get_element_bbox(result.element_id, snap)
                        if bbox:
                            verify_signals["elements_found"] = [
                                {
                                    "label": f"Element {result.element_id}",
                                    "bounding_box": bbox,
                                }
                            ]

                    verify_data = {
                        "passed": verify_passed,
                        "signals": verify_signals,
                    }

                    # Build elements data for pre field (include diff_status from snap_with_diff)
                    # Use the same format as build_snapshot_event for consistency
                    snapshot_event_data = TraceEventBuilder.build_snapshot_event(snap_with_diff)
                    pre_elements = snapshot_event_data.get("elements", [])

                    post_snapshot_digest = (
                        self._best_effort_post_snapshot_digest(goal) if self.tracer else None
                    )

                    # Build complete step_end event
                    step_end_data = TraceEventBuilder.build_step_end_event(
                        step_id=step_id,
                        step_index=self._step_count,
                        goal=goal,
                        attempt=attempt,
                        pre_url=pre_url,
                        post_url=post_url,
                        snapshot_digest=snapshot_digest,
                        post_snapshot_digest=post_snapshot_digest,
                        llm_data=llm_data,
                        exec_data=exec_data,
                        verify_data=verify_data,
                        pre_elements=pre_elements,
                    )

                    _safe_tracer_call(
                        self.tracer,
                        "emit",
                        self.verbose,
                        "step_end",
                        step_end_data,
                        step_id=step_id,
                    )

                post_url = self.browser.page.url if self.browser.page else None
                await _safe_hook_call_async(
                    on_step_end,
                    StepHookContext(
                        step_id=step_id,
                        step_index=self._step_count,
                        goal=goal,
                        attempt=attempt,
                        url=post_url,
                        success=result.success,
                        outcome=result.outcome,
                        error=result.error,
                    ),
                    self.verbose,
                )
                return result

            except Exception as e:
                # Emit error trace event if tracer is enabled
                if self.tracer:
                    _safe_tracer_call(
                        self.tracer,
                        "emit_error",
                        self.verbose,
                        step_id=step_id,
                        error=str(e),
                        attempt=attempt,
                    )

                if attempt < max_retries:
                    if self.verbose:
                        print(f"⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(1.0)  # Brief delay before retry
                    continue
                else:
                    # Emit step_end with whatever data we collected before failure
                    # This ensures diff_status and other fields are preserved in traces
                    if self.tracer and _step_snap_with_diff is not None:
                        post_url = self.browser.page.url if self.browser.page else None
                        snapshot_digest = f"sha256:{self._compute_hash(f'{_step_pre_url}{_step_snap_with_diff.timestamp}')}"

                        # Build pre_elements from snap_with_diff (includes diff_status)
                        snapshot_event_data = TraceEventBuilder.build_snapshot_event(
                            _step_snap_with_diff
                        )
                        pre_elements = snapshot_event_data.get("elements", [])

                        # Build LLM data if available
                        llm_data = None
                        if _step_llm_response:
                            llm_response_text = _step_llm_response.content
                            llm_response_hash = f"sha256:{self._compute_hash(llm_response_text)}"
                            llm_data = {
                                "response_text": llm_response_text,
                                "response_hash": llm_response_hash,
                                "usage": {
                                    "prompt_tokens": _step_llm_response.prompt_tokens or 0,
                                    "completion_tokens": _step_llm_response.completion_tokens or 0,
                                    "total_tokens": _step_llm_response.total_tokens or 0,
                                },
                            }

                        # Build exec data (failure state)
                        exec_data = {
                            "success": False,
                            "action": _step_result.action if _step_result else "error",
                            "outcome": str(e),
                            "duration_ms": _step_duration_ms,
                        }

                        # Build step_end event for failed step
                        step_end_data = TraceEventBuilder.build_step_end_event(
                            step_id=step_id,
                            step_index=self._step_count,
                            goal=goal,
                            attempt=attempt,
                            pre_url=_step_pre_url,
                            post_url=post_url,
                            snapshot_digest=snapshot_digest,
                            post_snapshot_digest=None,
                            llm_data=llm_data,
                            exec_data=exec_data,
                            verify_data=None,
                            pre_elements=pre_elements,
                        )

                        _safe_tracer_call(
                            self.tracer,
                            "emit",
                            self.verbose,
                            "step_end",
                            step_end_data,
                            step_id=step_id,
                        )

                    # Create error result
                    error_result = AgentActionResult(
                        success=False,
                        action="error",
                        goal=goal,
                        duration_ms=0,
                        attempt=attempt,
                        error=str(e),
                    )
                    self.history.append(
                        {
                            "goal": goal,
                            "action": "error",
                            "result": error_result.model_dump(),
                            "success": False,
                            "attempt": attempt,
                            "duration_ms": 0,
                        }
                    )
                    await _safe_hook_call_async(
                        on_step_end,
                        StepHookContext(
                            step_id=step_id,
                            step_index=self._step_count,
                            goal=goal,
                            attempt=attempt,
                            url=_step_pre_url,
                            success=False,
                            outcome="exception",
                            error=str(e),
                        ),
                        self.verbose,
                    )
                    raise RuntimeError(f"Failed after {max_retries} retries: {e}")

    def _track_tokens(self, goal: str, llm_response: LLMResponse):
        """Track token usage for analytics (same as sync version)"""
        if llm_response.prompt_tokens:
            self._token_usage_raw["total_prompt_tokens"] += llm_response.prompt_tokens
        if llm_response.completion_tokens:
            self._token_usage_raw["total_completion_tokens"] += llm_response.completion_tokens
        if llm_response.total_tokens:
            self._token_usage_raw["total_tokens"] += llm_response.total_tokens

        self._token_usage_raw["by_action"].append(
            {
                "goal": goal,
                "prompt_tokens": llm_response.prompt_tokens or 0,
                "completion_tokens": llm_response.completion_tokens or 0,
                "total_tokens": llm_response.total_tokens or 0,
                "model": llm_response.model_name,
            }
        )

    def get_token_stats(self) -> TokenStats:
        """Get token usage statistics (same as sync version)"""
        by_action = [ActionTokenUsage(**action) for action in self._token_usage_raw["by_action"]]
        return TokenStats(
            total_prompt_tokens=self._token_usage_raw["total_prompt_tokens"],
            total_completion_tokens=self._token_usage_raw["total_completion_tokens"],
            total_tokens=self._token_usage_raw["total_tokens"],
            by_action=by_action,
        )

    def get_history(self) -> list[ActionHistory]:
        """Get execution history (same as sync version)"""
        return [ActionHistory(**h) for h in self.history]

    def clear_history(self) -> None:
        """Clear execution history and reset token counters (same as sync version)"""
        self.history.clear()
        self._token_usage_raw = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "by_action": [],
        }

    def filter_elements(self, snapshot: Snapshot, goal: str | None = None) -> list[Element]:
        """
        Filter elements from snapshot based on goal context.

        This implementation uses ElementFilter to apply goal-based keyword matching
        to boost relevant elements and filters out irrelevant ones.

        Args:
            snapshot: Current page snapshot
            goal: User's goal (can inform filtering)

        Returns:
            Filtered list of elements
        """
        return ElementFilter.filter_by_goal(snapshot, goal, self.default_snapshot_limit)
