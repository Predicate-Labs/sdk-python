"""
Sentience Agent: High-level automation agent using LLM + SDK
Implements observe-think-act loop for natural language commands
"""

import re
import time
from typing import Dict, Any, List, Optional
from .llm_provider import LLMProvider, LLMResponse
from .browser import SentienceBrowser
from .snapshot import snapshot
from .actions import click, type_text, press
from .models import Snapshot, Element, ActionResult


class SentienceAgent:
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
        snapshot_limit: int = 50,
        verbose: bool = True
    ):
        """
        Initialize Sentience Agent

        Args:
            browser: SentienceBrowser instance
            llm: LLM provider (OpenAIProvider, AnthropicProvider, etc.)
            snapshot_limit: Maximum elements to include in context (default: 50)
            verbose: Print execution logs (default: True)
        """
        self.browser = browser
        self.llm = llm
        self.snapshot_limit = snapshot_limit
        self.verbose = verbose

        # Execution history
        self.history: List[Dict[str, Any]] = []

        # Token usage tracking
        self.token_usage = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "by_action": []
        }

    def act(
        self,
        goal: str,
        max_retries: int = 2,
        snapshot_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a high-level goal using observe → think → act loop

        Args:
            goal: Natural language instruction (e.g., "Click the Sign In button")
            max_retries: Number of retries on failure (default: 2)
            snapshot_options: Optional snapshot parameters (limit, filter, etc.)

        Returns:
            Result dict with status, action_taken, reasoning, and execution data

        Example:
            >>> result = agent.act("Click the search box")
            >>> print(result)
            {'success': True, 'action': 'click', 'element_id': 42, 'reasoning': '...'}
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🤖 Agent Goal: {goal}")
            print(f"{'='*70}")

        for attempt in range(max_retries + 1):
            try:
                # 1. OBSERVE: Get refined semantic snapshot
                start_time = time.time()

                snap_opts = snapshot_options or {}
                snap_opts.setdefault('limit', self.snapshot_limit)

                snap = snapshot(self.browser, **snap_opts)

                if snap.status != "success":
                    raise RuntimeError(f"Snapshot failed: {snap.error}")

                # 2. GROUND: Format elements for LLM context
                context = self._build_context(snap, goal)

                # 3. THINK: Query LLM for next action
                llm_response = self._query_llm(context, goal)

                if self.verbose:
                    print(f"🧠 LLM Decision: {llm_response.content}")

                # Track token usage
                self._track_tokens(goal, llm_response)

                # Parse action from LLM response
                action_str = llm_response.content.strip()

                # 4. EXECUTE: Parse and run action
                result = self._execute_action(action_str, snap)

                duration_ms = int((time.time() - start_time) * 1000)
                result['duration_ms'] = duration_ms
                result['attempt'] = attempt
                result['goal'] = goal

                # 5. RECORD: Track history
                self.history.append({
                    "goal": goal,
                    "action": action_str,
                    "result": result,
                    "success": result.get("success", False),
                    "attempt": attempt,
                    "duration_ms": duration_ms
                })

                if self.verbose:
                    status = "✅" if result.get("success") else "❌"
                    print(f"{status} Completed in {duration_ms}ms")

                return result

            except Exception as e:
                if attempt < max_retries:
                    if self.verbose:
                        print(f"⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                    time.sleep(1.0)  # Brief delay before retry
                    continue
                else:
                    error_result = {
                        "success": False,
                        "goal": goal,
                        "error": str(e),
                        "attempt": attempt
                    }
                    self.history.append(error_result)
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
        for el in snap.elements[:self.snapshot_limit]:
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
            text_preview = (el.text[:50] + "...") if el.text and len(el.text) > 50 else (el.text or "")

            lines.append(
                f"[{el.id}] <{el.role}> \"{text_preview}\"{cues_str} "
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

VISIBLE ELEMENTS (sorted by importance, max {self.snapshot_limit}):
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

    def _execute_action(self, action_str: str, snap: Snapshot) -> Dict[str, Any]:
        """
        Parse action string and execute SDK call

        Args:
            action_str: Action string from LLM (e.g., "CLICK(42)")
            snap: Current snapshot (for context)

        Returns:
            Execution result dictionary
        """
        # Parse CLICK(42)
        if match := re.match(r'CLICK\s*\(\s*(\d+)\s*\)', action_str, re.IGNORECASE):
            element_id = int(match.group(1))
            result = click(self.browser, element_id)
            return {
                "success": result.success,
                "action": "click",
                "element_id": element_id,
                "outcome": result.outcome,
                "url_changed": result.url_changed
            }

        # Parse TYPE(42, "hello world")
        elif match := re.match(r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)', action_str, re.IGNORECASE):
            element_id = int(match.group(1))
            text = match.group(2)
            result = type_text(self.browser, element_id, text)
            return {
                "success": result.success,
                "action": "type",
                "element_id": element_id,
                "text": text,
                "outcome": result.outcome
            }

        # Parse PRESS("Enter")
        elif match := re.match(r'PRESS\s*\(\s*["\']([^"\']+)["\']\s*\)', action_str, re.IGNORECASE):
            key = match.group(1)
            result = press(self.browser, key)
            return {
                "success": result.success,
                "action": "press",
                "key": key,
                "outcome": result.outcome
            }

        # Parse FINISH()
        elif re.match(r'FINISH\s*\(\s*\)', action_str, re.IGNORECASE):
            return {
                "success": True,
                "action": "finish",
                "message": "Task marked as complete"
            }

        else:
            raise ValueError(
                f"Unknown action format: {action_str}\n"
                f"Expected: CLICK(id), TYPE(id, \"text\"), PRESS(\"key\"), or FINISH()"
            )

    def _track_tokens(self, goal: str, llm_response: LLMResponse):
        """
        Track token usage for analytics

        Args:
            goal: User goal
            llm_response: LLM response with token usage
        """
        if llm_response.prompt_tokens:
            self.token_usage["total_prompt_tokens"] += llm_response.prompt_tokens
        if llm_response.completion_tokens:
            self.token_usage["total_completion_tokens"] += llm_response.completion_tokens
        if llm_response.total_tokens:
            self.token_usage["total_tokens"] += llm_response.total_tokens

        self.token_usage["by_action"].append({
            "goal": goal,
            "prompt_tokens": llm_response.prompt_tokens,
            "completion_tokens": llm_response.completion_tokens,
            "total_tokens": llm_response.total_tokens,
            "model": llm_response.model_name
        })

    def get_token_stats(self) -> Dict[str, Any]:
        """
        Get token usage statistics

        Returns:
            Dictionary with token usage breakdown
        """
        return self.token_usage.copy()

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get execution history

        Returns:
            List of all actions taken with results
        """
        return self.history.copy()

    def clear_history(self):
        """Clear execution history and reset token counters"""
        self.history.clear()
        self.token_usage = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "by_action": []
        }
