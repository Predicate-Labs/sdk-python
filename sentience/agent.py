"""
Sentience Agent: High-level automation agent using LLM + SDK
Implements observe-think-act loop for natural language commands
"""

import asyncio
import hashlib
import re
import time
from typing import TYPE_CHECKING, Any, Optional

from .actions import click, click_async, press, press_async, type_text, type_text_async
from .agent_config import AgentConfig
from .base_agent import BaseAgent, BaseAgentAsync
from .browser import AsyncSentienceBrowser, SentienceBrowser
from .llm_provider import LLMProvider, LLMResponse
from .models import (
    ActionHistory,
    ActionTokenUsage,
    AgentActionResult,
    Element,
    ScreenshotConfig,
    Snapshot,
    SnapshotOptions,
    TokenStats,
)
from .snapshot import snapshot, snapshot_async

if TYPE_CHECKING:
    from .tracing import Tracer


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
        browser: SentienceBrowser,
        llm: LLMProvider,
        default_snapshot_limit: int = 50,
        verbose: bool = True,
        tracer: Optional["Tracer"] = None,
        config: Optional["AgentConfig"] = None,
    ):
        """
        Initialize Sentience Agent

        Args:
            browser: SentienceBrowser instance
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

    def act(  # noqa: C901
        self,
        goal: str,
        max_retries: int = 2,
        snapshot_options: SnapshotOptions | None = None,
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

        # Emit step_start trace event if tracer is enabled
        if self.tracer:
            pre_url = self.browser.page.url if self.browser.page else None
            self.tracer.emit_step_start(
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                pre_url=pre_url,
            )

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

                # Apply element filtering based on goal
                filtered_elements = self.filter_elements(snap, goal)

                # Emit snapshot trace event if tracer is enabled
                if self.tracer:
                    # Include ALL elements with full data for DOM tree display
                    # Use snap.elements (all elements) not filtered_elements
                    elements_data = [el.model_dump() for el in snap.elements]

                    # Build snapshot event data
                    snapshot_data = {
                        "url": snap.url,
                        "element_count": len(snap.elements),
                        "timestamp": snap.timestamp,
                        "elements": elements_data,  # Full element data for DOM tree
                    }

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

                    self.tracer.emit(
                        "snapshot",
                        snapshot_data,
                        step_id=step_id,
                    )

                # Create filtered snapshot
                filtered_snap = Snapshot(
                    status=snap.status,
                    timestamp=snap.timestamp,
                    url=snap.url,
                    viewport=snap.viewport,
                    elements=filtered_elements,
                    screenshot=snap.screenshot,
                    screenshot_format=snap.screenshot_format,
                    error=snap.error,
                )

                # 2. GROUND: Format elements for LLM context
                context = self._build_context(filtered_snap, goal)

                # 3. THINK: Query LLM for next action
                llm_response = self._query_llm(context, goal)

                # Emit LLM query trace event if tracer is enabled
                if self.tracer:
                    self.tracer.emit(
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
                action_str = self._extract_action_from_response(llm_response.content)

                # 4. EXECUTE: Parse and run action
                result_dict = self._execute_action(action_str, filtered_snap)

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

                    self.tracer.emit(
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

                    # Build complete step_end event
                    step_end_data = {
                        "v": 1,
                        "step_id": step_id,
                        "step_index": self._step_count,
                        "goal": goal,
                        "attempt": attempt,
                        "pre": {
                            "url": pre_url,
                            "snapshot_digest": snapshot_digest,
                        },
                        "llm": llm_data,
                        "exec": exec_data,
                        "post": {
                            "url": post_url,
                        },
                        "verify": verify_data,
                    }

                    self.tracer.emit("step_end", step_end_data, step_id=step_id)

                return result

            except Exception as e:
                # Emit error trace event if tracer is enabled
                if self.tracer:
                    self.tracer.emit_error(step_id=step_id, error=str(e), attempt=attempt)

                if attempt < max_retries:
                    if self.verbose:
                        print(f"⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                    time.sleep(1.0)  # Brief delay before retry
                    continue
                else:
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
                    raise RuntimeError(f"Failed after {max_retries} retries: {e}")

    def _build_context(self, snap: Snapshot, goal: str) -> str:
        """
        Convert snapshot elements to token-efficient prompt string

        Format: [ID] <role> "text" {cues} @ (x,y) (Imp:score)

        Args:
            snap: Snapshot object
            goal: User goal (for context)

        Returns:
            Formatted element context string
        """
        lines = []
        # Note: elements are already filtered by filter_elements() in act()
        for el in snap.elements:
            # Extract visual cues
            cues = []
            if el.visual_cues.is_primary:
                cues.append("PRIMARY")
            if el.visual_cues.is_clickable:
                cues.append("CLICKABLE")
            if el.visual_cues.background_color_name:
                cues.append(f"color:{el.visual_cues.background_color_name}")

            # Format element line
            cues_str = f" {{{','.join(cues)}}}" if cues else ""
            text_preview = (
                (el.text[:50] + "...") if el.text and len(el.text) > 50 else (el.text or "")
            )

            lines.append(
                f'[{el.id}] <{el.role}> "{text_preview}"{cues_str} '
                f"@ ({int(el.bbox.x)},{int(el.bbox.y)}) (Imp:{el.importance})"
            )

        return "\n".join(lines)

    def _extract_action_from_response(self, response: str) -> str:
        """
        Extract action command from LLM response, handling cases where
        the LLM adds extra explanation despite instructions.

        Args:
            response: Raw LLM response text

        Returns:
            Cleaned action command string
        """
        import re

        # Remove markdown code blocks if present
        response = re.sub(r"```[\w]*\n?", "", response)
        response = response.strip()

        # Try to find action patterns in the response
        # Pattern matches: CLICK(123), TYPE(123, "text"), PRESS("key"), FINISH()
        action_pattern = r'(CLICK\s*\(\s*\d+\s*\)|TYPE\s*\(\s*\d+\s*,\s*["\'].*?["\']\s*\)|PRESS\s*\(\s*["\'].*?["\']\s*\)|FINISH\s*\(\s*\))'

        match = re.search(action_pattern, response, re.IGNORECASE)
        if match:
            return match.group(1)

        # If no pattern match, return the original response (will likely fail parsing)
        return response

    def _query_llm(self, dom_context: str, goal: str) -> LLMResponse:
        """
        Query LLM with standardized prompt template

        Args:
            dom_context: Formatted element context
            goal: User goal

        Returns:
            LLMResponse from LLM provider
        """
        system_prompt = f"""You are an AI web automation agent.

GOAL: {goal}

VISIBLE ELEMENTS (sorted by importance):
{dom_context}

VISUAL CUES EXPLAINED:
- {{PRIMARY}}: Main call-to-action element on the page
- {{CLICKABLE}}: Element is clickable
- {{color:X}}: Background color name

CRITICAL RESPONSE FORMAT:
You MUST respond with ONLY ONE of these exact action formats:
- CLICK(id) - Click element by ID
- TYPE(id, "text") - Type text into element
- PRESS("key") - Press keyboard key (Enter, Escape, Tab, ArrowDown, etc)
- FINISH() - Task complete

DO NOT include any explanation, reasoning, or natural language.
DO NOT use markdown formatting or code blocks.
DO NOT say "The next step is..." or anything similar.

CORRECT Examples:
CLICK(42)
TYPE(15, "magic mouse")
PRESS("Enter")
FINISH()

INCORRECT Examples (DO NOT DO THIS):
"The next step is to click..."
"I will type..."
```CLICK(42)```
"""

        user_prompt = "Return the single action command:"

        return self.llm.generate(system_prompt, user_prompt, temperature=0.0)

    def _execute_action(self, action_str: str, snap: Snapshot) -> dict[str, Any]:
        """
        Parse action string and execute SDK call

        Args:
            action_str: Action string from LLM (e.g., "CLICK(42)")
            snap: Current snapshot (for context)

        Returns:
            Execution result dictionary
        """
        # Parse CLICK(42)
        if match := re.match(r"CLICK\s*\(\s*(\d+)\s*\)", action_str, re.IGNORECASE):
            element_id = int(match.group(1))
            result = click(self.browser, element_id)
            return {
                "success": result.success,
                "action": "click",
                "element_id": element_id,
                "outcome": result.outcome,
                "url_changed": result.url_changed,
            }

        # Parse TYPE(42, "hello world")
        elif match := re.match(
            r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)',
            action_str,
            re.IGNORECASE,
        ):
            element_id = int(match.group(1))
            text = match.group(2)
            result = type_text(self.browser, element_id, text)
            return {
                "success": result.success,
                "action": "type",
                "element_id": element_id,
                "text": text,
                "outcome": result.outcome,
            }

        # Parse PRESS("Enter")
        elif match := re.match(r'PRESS\s*\(\s*["\']([^"\']+)["\']\s*\)', action_str, re.IGNORECASE):
            key = match.group(1)
            result = press(self.browser, key)
            return {
                "success": result.success,
                "action": "press",
                "key": key,
                "outcome": result.outcome,
            }

        # Parse FINISH()
        elif re.match(r"FINISH\s*\(\s*\)", action_str, re.IGNORECASE):
            return {
                "success": True,
                "action": "finish",
                "message": "Task marked as complete",
            }

        else:
            raise ValueError(
                f"Unknown action format: {action_str}\n"
                f'Expected: CLICK(id), TYPE(id, "text"), PRESS("key"), or FINISH()'
            )

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

        This default implementation applies goal-based keyword matching to boost
        relevant elements and filters out irrelevant ones.

        Args:
            snapshot: Current page snapshot
            goal: User's goal (can inform filtering)

        Returns:
            Filtered list of elements
        """
        elements = snapshot.elements

        # If no goal provided, return all elements (up to limit)
        if not goal:
            return elements[: self.default_snapshot_limit]

        goal_lower = goal.lower()

        # Extract keywords from goal
        keywords = self._extract_keywords(goal_lower)

        # Boost elements matching goal keywords
        scored_elements = []
        for el in elements:
            score = el.importance

            # Boost if element text matches goal
            if el.text and any(kw in el.text.lower() for kw in keywords):
                score += 0.3

            # Boost if role matches goal intent
            if "click" in goal_lower and el.visual_cues.is_clickable:
                score += 0.2
            if "type" in goal_lower and el.role in ["textbox", "searchbox"]:
                score += 0.2
            if "search" in goal_lower:
                # Filter out non-interactive elements for search tasks
                if el.role in ["link", "img"] and not el.visual_cues.is_primary:
                    score -= 0.5

            scored_elements.append((score, el))

        # Re-sort by boosted score
        scored_elements.sort(key=lambda x: x[0], reverse=True)
        elements = [el for _, el in scored_elements]

        return elements[: self.default_snapshot_limit]

    def _extract_keywords(self, text: str) -> list[str]:
        """
        Extract meaningful keywords from goal text

        Args:
            text: Text to extract keywords from

        Returns:
            List of keywords
        """
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
        }
        words = text.split()
        return [w for w in words if w not in stopwords and len(w) > 2]


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

        # Emit step_start trace event if tracer is enabled
        if self.tracer:
            pre_url = self.browser.page.url if self.browser.page else None
            self.tracer.emit_step_start(
                step_id=step_id,
                step_index=self._step_count,
                goal=goal,
                attempt=0,
                pre_url=pre_url,
            )

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

                # Apply element filtering based on goal
                filtered_elements = self.filter_elements(snap, goal)

                # Emit snapshot trace event if tracer is enabled
                if self.tracer:
                    # Include ALL elements with full data for DOM tree display
                    # Use snap.elements (all elements) not filtered_elements
                    elements_data = [el.model_dump() for el in snap.elements]

                    # Build snapshot event data
                    snapshot_data = {
                        "url": snap.url,
                        "element_count": len(snap.elements),
                        "timestamp": snap.timestamp,
                        "elements": elements_data,  # Full element data for DOM tree
                    }

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

                    self.tracer.emit(
                        "snapshot",
                        snapshot_data,
                        step_id=step_id,
                    )

                # Create filtered snapshot
                filtered_snap = Snapshot(
                    status=snap.status,
                    timestamp=snap.timestamp,
                    url=snap.url,
                    viewport=snap.viewport,
                    elements=filtered_elements,
                    screenshot=snap.screenshot,
                    screenshot_format=snap.screenshot_format,
                    error=snap.error,
                )

                # 2. GROUND: Format elements for LLM context
                context = self._build_context(filtered_snap, goal)

                # 3. THINK: Query LLM for next action
                llm_response = self._query_llm(context, goal)

                # Emit LLM query trace event if tracer is enabled
                if self.tracer:
                    self.tracer.emit(
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
                action_str = self._extract_action_from_response(llm_response.content)

                # 4. EXECUTE: Parse and run action
                result_dict = await self._execute_action(action_str, filtered_snap)

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

                    self.tracer.emit(
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

                    # Build complete step_end event
                    step_end_data = {
                        "v": 1,
                        "step_id": step_id,
                        "step_index": self._step_count,
                        "goal": goal,
                        "attempt": attempt,
                        "pre": {
                            "url": pre_url,
                            "snapshot_digest": snapshot_digest,
                        },
                        "llm": llm_data,
                        "exec": exec_data,
                        "post": {
                            "url": post_url,
                        },
                        "verify": verify_data,
                    }

                    self.tracer.emit("step_end", step_end_data, step_id=step_id)

                return result

            except Exception as e:
                # Emit error trace event if tracer is enabled
                if self.tracer:
                    self.tracer.emit_error(step_id=step_id, error=str(e), attempt=attempt)

                if attempt < max_retries:
                    if self.verbose:
                        print(f"⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(1.0)  # Brief delay before retry
                    continue
                else:
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
                    raise RuntimeError(f"Failed after {max_retries} retries: {e}")

    def _build_context(self, snap: Snapshot, goal: str) -> str:
        """Convert snapshot elements to token-efficient prompt string (same as sync version)"""
        lines = []
        # Note: elements are already filtered by filter_elements() in act()
        for el in snap.elements:
            # Extract visual cues
            cues = []
            if el.visual_cues.is_primary:
                cues.append("PRIMARY")
            if el.visual_cues.is_clickable:
                cues.append("CLICKABLE")
            if el.visual_cues.background_color_name:
                cues.append(f"color:{el.visual_cues.background_color_name}")

            # Format element line
            cues_str = f" {{{','.join(cues)}}}" if cues else ""
            text_preview = (
                (el.text[:50] + "...") if el.text and len(el.text) > 50 else (el.text or "")
            )

            lines.append(
                f'[{el.id}] <{el.role}> "{text_preview}"{cues_str} '
                f"@ ({int(el.bbox.x)},{int(el.bbox.y)}) (Imp:{el.importance})"
            )

        return "\n".join(lines)

    def _extract_action_from_response(self, response: str) -> str:
        """Extract action command from LLM response (same as sync version)"""
        # Remove markdown code blocks if present
        response = re.sub(r"```[\w]*\n?", "", response)
        response = response.strip()

        # Try to find action patterns in the response
        # Pattern matches: CLICK(123), TYPE(123, "text"), PRESS("key"), FINISH()
        action_pattern = r'(CLICK\s*\(\s*\d+\s*\)|TYPE\s*\(\s*\d+\s*,\s*["\'].*?["\']\s*\)|PRESS\s*\(\s*["\'].*?["\']\s*\)|FINISH\s*\(\s*\))'

        match = re.search(action_pattern, response, re.IGNORECASE)
        if match:
            return match.group(1)

        # If no pattern match, return the original response (will likely fail parsing)
        return response

    def _query_llm(self, dom_context: str, goal: str) -> LLMResponse:
        """Query LLM with standardized prompt template (same as sync version)"""
        system_prompt = f"""You are an AI web automation agent.

GOAL: {goal}

VISIBLE ELEMENTS (sorted by importance):
{dom_context}

VISUAL CUES EXPLAINED:
- {{PRIMARY}}: Main call-to-action element on the page
- {{CLICKABLE}}: Element is clickable
- {{color:X}}: Background color name

CRITICAL RESPONSE FORMAT:
You MUST respond with ONLY ONE of these exact action formats:
- CLICK(id) - Click element by ID
- TYPE(id, "text") - Type text into element
- PRESS("key") - Press keyboard key (Enter, Escape, Tab, ArrowDown, etc)
- FINISH() - Task complete

DO NOT include any explanation, reasoning, or natural language.
DO NOT use markdown formatting or code blocks.
DO NOT say "The next step is..." or anything similar.

CORRECT Examples:
CLICK(42)
TYPE(15, "magic mouse")
PRESS("Enter")
FINISH()

INCORRECT Examples (DO NOT DO THIS):
"The next step is to click..."
"I will type..."
```CLICK(42)```
"""

        user_prompt = "Return the single action command:"

        return self.llm.generate(system_prompt, user_prompt, temperature=0.0)

    async def _execute_action(self, action_str: str, snap: Snapshot) -> dict[str, Any]:
        """
        Parse action string and execute SDK call (async)

        Args:
            action_str: Action string from LLM (e.g., "CLICK(42)")
            snap: Current snapshot (for context)

        Returns:
            Execution result dictionary
        """
        # Parse CLICK(42)
        if match := re.match(r"CLICK\s*\(\s*(\d+)\s*\)", action_str, re.IGNORECASE):
            element_id = int(match.group(1))
            result = await click_async(self.browser, element_id)
            return {
                "success": result.success,
                "action": "click",
                "element_id": element_id,
                "outcome": result.outcome,
                "url_changed": result.url_changed,
            }

        # Parse TYPE(42, "hello world")
        elif match := re.match(
            r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)',
            action_str,
            re.IGNORECASE,
        ):
            element_id = int(match.group(1))
            text = match.group(2)
            result = await type_text_async(self.browser, element_id, text)
            return {
                "success": result.success,
                "action": "type",
                "element_id": element_id,
                "text": text,
                "outcome": result.outcome,
            }

        # Parse PRESS("Enter")
        elif match := re.match(r'PRESS\s*\(\s*["\']([^"\']+)["\']\s*\)', action_str, re.IGNORECASE):
            key = match.group(1)
            result = await press_async(self.browser, key)
            return {
                "success": result.success,
                "action": "press",
                "key": key,
                "outcome": result.outcome,
            }

        # Parse FINISH()
        elif re.match(r"FINISH\s*\(\s*\)", action_str, re.IGNORECASE):
            return {
                "success": True,
                "action": "finish",
                "message": "Task marked as complete",
            }

        else:
            raise ValueError(
                f"Unknown action format: {action_str}\n"
                f'Expected: CLICK(id), TYPE(id, "text"), PRESS("key"), or FINISH()'
            )

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
        """Filter elements from snapshot based on goal context (same as sync version)"""
        elements = snapshot.elements

        # If no goal provided, return all elements (up to limit)
        if not goal:
            return elements[: self.default_snapshot_limit]

        goal_lower = goal.lower()

        # Extract keywords from goal
        keywords = self._extract_keywords(goal_lower)

        # Boost elements matching goal keywords
        scored_elements = []
        for el in elements:
            score = el.importance

            # Boost if element text matches goal
            if el.text and any(kw in el.text.lower() for kw in keywords):
                score += 0.3

            # Boost if role matches goal intent
            if "click" in goal_lower and el.visual_cues.is_clickable:
                score += 0.2
            if "type" in goal_lower and el.role in ["textbox", "searchbox"]:
                score += 0.2
            if "search" in goal_lower:
                # Filter out non-interactive elements for search tasks
                if el.role in ["link", "img"] and not el.visual_cues.is_primary:
                    score -= 0.5

            scored_elements.append((score, el))

        # Re-sort by boosted score
        scored_elements.sort(key=lambda x: x[0], reverse=True)
        elements = [el for _, el in scored_elements]

        return elements[: self.default_snapshot_limit]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from goal text (same as sync version)"""
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
        }
        words = text.split()
        return [w for w in words if w not in stopwords and len(w) > 2]
