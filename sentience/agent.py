"""
Sentience Agent: High-level automation agent using LLM + SDK
Implements observe-think-act loop for natural language commands
"""

import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .actions import click, press, type_text
from .base_agent import BaseAgent
from .browser import SentienceBrowser
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
from .snapshot import snapshot

if TYPE_CHECKING:
    from .agent_config import AgentConfig
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
        self.config = config

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

    def act(
        self, goal: str, max_retries: int = 2, snapshot_options: SnapshotOptions | None = None
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
            print(f"\n{'='*70}")
            print(f"🤖 Agent Goal: {goal}")
            print(f"{'='*70}")

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

                # Convert screenshot config to dict if needed
                screenshot_param = snap_opts.screenshot
                if isinstance(snap_opts.screenshot, ScreenshotConfig):
                    screenshot_param = {
                        "format": snap_opts.screenshot.format,
                        "quality": snap_opts.screenshot.quality,
                    }

                # Call snapshot with converted parameters
                snap = snapshot(
                    self.browser,
                    screenshot=screenshot_param,
                    limit=snap_opts.limit,
                    filter=snap_opts.filter.model_dump() if snap_opts.filter else None,
                    use_api=snap_opts.use_api,
                )

                if snap.status != "success":
                    raise RuntimeError(f"Snapshot failed: {snap.error}")

                # Apply element filtering based on goal
                filtered_elements = self.filter_elements(snap, goal)

                # Emit snapshot trace event if tracer is enabled
                if self.tracer:
                    # Include element data for live overlay visualization
                    # Use filtered_elements for overlay (only relevant elements)
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
                            "text": el.text[:50] if el.text else "",  # Truncate for brevity
                        }
                        for el in filtered_elements[:50]  # Limit to first 50 for performance
                    ]

                    self.tracer.emit(
                        "snapshot",
                        {
                            "url": snap.url,
                            "element_count": len(snap.elements),
                            "timestamp": snap.timestamp,
                            "elements": elements_data,  # Add element data for overlay
                        },
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
                action_str = llm_response.content.strip()

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
                    self.tracer.emit(
                        "step_end",
                        {
                            "success": result.success,
                            "duration_ms": duration_ms,
                            "action": result.action,
                        },
                        step_id=step_id,
                    )

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

RESPONSE FORMAT:
Return ONLY the function call, no explanation or markdown.

Available actions:
- CLICK(id) - Click element by ID
- TYPE(id, "text") - Type text into element
- PRESS("key") - Press keyboard key (Enter, Escape, Tab, ArrowDown, etc)
- FINISH() - Task complete

Examples:
- CLICK(42)
- TYPE(15, "magic mouse")
- PRESS("Enter")
- FINISH()
"""

        user_prompt = "What is the next step to achieve the goal?"

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
            r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)', action_str, re.IGNORECASE
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
            return {"success": True, "action": "finish", "message": "Task marked as complete"}

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
