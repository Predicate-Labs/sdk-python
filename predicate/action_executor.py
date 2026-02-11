"""
Action Executor for Sentience Agent.

Handles parsing and execution of action commands (CLICK, TYPE, PRESS, FINISH).
This separates action execution concerns from LLM interaction.
"""

import re
from typing import Any, Union

from .actions import click, click_async, press, press_async, type_text, type_text_async
from .browser import AsyncSentienceBrowser, SentienceBrowser
from .models import Snapshot
from .protocols import AsyncBrowserProtocol, BrowserProtocol


class ActionExecutor:
    """
    Executes actions and handles parsing of action command strings.

    This class encapsulates all action execution logic, making it easier to:
    - Test action execution independently
    - Add new action types in one place
    - Handle action parsing errors consistently
    """

    def __init__(
        self,
        browser: SentienceBrowser | AsyncSentienceBrowser | BrowserProtocol | AsyncBrowserProtocol,
    ):
        """
        Initialize action executor.

        Args:
            browser: SentienceBrowser, AsyncSentienceBrowser, or protocol-compatible instance
                    (for testing, can use mock objects that implement BrowserProtocol)
        """
        self.browser = browser
        # Check if browser is async - support both concrete types and protocols
        # Check concrete types first (most reliable)
        if isinstance(browser, AsyncSentienceBrowser):
            self._is_async = True
        elif isinstance(browser, SentienceBrowser):
            self._is_async = False
        else:
            # For protocol-based browsers, check if methods are actually async
            # This is more reliable than isinstance checks which can match both protocols
            import inspect

            start_method = getattr(browser, "start", None)
            if start_method and inspect.iscoroutinefunction(start_method):
                self._is_async = True
            elif isinstance(browser, BrowserProtocol):
                # If it implements BrowserProtocol and start is not async, it's sync
                self._is_async = False
            else:
                # Default to sync for unknown types
                self._is_async = False

    def execute(self, action_str: str, snap: Snapshot) -> dict[str, Any]:
        """
        Parse action string and execute SDK call (synchronous).

        Args:
            action_str: Action string from LLM (e.g., "CLICK(42)", "TYPE(15, \"text\")")
            snap: Current snapshot (for context, currently unused but kept for API consistency)

        Returns:
            Execution result dictionary with keys:
            - success: bool
            - action: str (e.g., "click", "type", "press", "finish")
            - element_id: Optional[int] (for click/type actions)
            - text: Optional[str] (for type actions)
            - key: Optional[str] (for press actions)
            - outcome: Optional[str] (action outcome)
            - url_changed: Optional[bool] (for click actions)
            - error: Optional[str] (if action failed)
            - message: Optional[str] (for finish action)

        Raises:
            ValueError: If action format is unknown
            RuntimeError: If called on async browser (use execute_async instead)
        """
        if self._is_async:
            raise RuntimeError(
                "ActionExecutor.execute() called on async browser. Use execute_async() instead."
            )

        # Parse CLICK(42)
        if match := re.match(r"CLICK\s*\(\s*(\d+)\s*\)", action_str, re.IGNORECASE):
            element_id = int(match.group(1))
            result = click(self.browser, element_id)  # type: ignore
            return {
                "success": result.success,
                "action": "click",
                "element_id": element_id,
                "outcome": result.outcome,
                "url_changed": result.url_changed,
                "cursor": getattr(result, "cursor", None),
            }

        # Parse TYPE(42, "hello world")
        elif match := re.match(
            r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)',
            action_str,
            re.IGNORECASE,
        ):
            element_id = int(match.group(1))
            text = match.group(2)
            result = type_text(self.browser, element_id, text)  # type: ignore
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
            result = press(self.browser, key)  # type: ignore
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

    async def execute_async(self, action_str: str, snap: Snapshot) -> dict[str, Any]:
        """
        Parse action string and execute SDK call (asynchronous).

        Args:
            action_str: Action string from LLM (e.g., "CLICK(42)", "TYPE(15, \"text\")")
            snap: Current snapshot (for context, currently unused but kept for API consistency)

        Returns:
            Execution result dictionary (same format as execute())

        Raises:
            ValueError: If action format is unknown
            RuntimeError: If called on sync browser (use execute() instead)
        """
        if not self._is_async:
            raise RuntimeError(
                "ActionExecutor.execute_async() called on sync browser. Use execute() instead."
            )

        # Parse CLICK(42)
        if match := re.match(r"CLICK\s*\(\s*(\d+)\s*\)", action_str, re.IGNORECASE):
            element_id = int(match.group(1))
            result = await click_async(self.browser, element_id)  # type: ignore
            return {
                "success": result.success,
                "action": "click",
                "element_id": element_id,
                "outcome": result.outcome,
                "url_changed": result.url_changed,
                "cursor": getattr(result, "cursor", None),
            }

        # Parse TYPE(42, "hello world")
        elif match := re.match(
            r'TYPE\s*\(\s*(\d+)\s*,\s*["\']([^"\']*)["\']\s*\)',
            action_str,
            re.IGNORECASE,
        ):
            element_id = int(match.group(1))
            text = match.group(2)
            result = await type_text_async(self.browser, element_id, text)  # type: ignore
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
            result = await press_async(self.browser, key)  # type: ignore
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
