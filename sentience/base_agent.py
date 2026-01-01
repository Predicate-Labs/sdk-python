"""
BaseAgent: Abstract base class for all Sentience agents
Defines the interface that all agent implementations must follow
"""

from abc import ABC, abstractmethod

from .models import ActionHistory, AgentActionResult, Element, Snapshot, TokenStats


class BaseAgent(ABC):
    """
    Abstract base class for all Sentience agents.

    Provides a standard interface for:
    - Executing natural language goals (act)
    - Tracking execution history
    - Monitoring token usage
    - Filtering elements based on goals

    Subclasses must implement:
    - act(): Execute a natural language goal
    - get_history(): Return execution history
    - get_token_stats(): Return token usage statistics
    - clear_history(): Reset history and token counters

    Subclasses can override:
    - filter_elements(): Customize element filtering logic
    """

    @abstractmethod
    def act(self, goal: str, **kwargs) -> AgentActionResult:
        """
        Execute a natural language goal using the agent.

        Args:
            goal: Natural language instruction (e.g., "Click the login button")
            **kwargs: Additional parameters (implementation-specific)

        Returns:
            AgentActionResult with execution details

        Raises:
            RuntimeError: If execution fails after retries
        """
        pass

    @abstractmethod
    def get_history(self) -> list[ActionHistory]:
        """
        Get the execution history of all actions taken.

        Returns:
            List of ActionHistory entries
        """
        pass

    @abstractmethod
    def get_token_stats(self) -> TokenStats:
        """
        Get token usage statistics for the agent session.

        Returns:
            TokenStats with cumulative token counts
        """
        pass

    @abstractmethod
    def clear_history(self) -> None:
        """
        Clear execution history and reset token counters.

        This resets the agent to a clean state.
        """
        pass

    def filter_elements(self, snapshot: Snapshot, goal: str | None = None) -> list[Element]:
        """
        Filter elements from a snapshot based on goal context.

        Default implementation returns all elements unchanged.
        Subclasses can override to implement custom filtering logic
        such as:
        - Removing irrelevant elements based on goal keywords
        - Boosting importance of matching elements
        - Filtering by role, size, or visual properties

        Args:
            snapshot: Current page snapshot
            goal: User's goal (can inform filtering strategy)

        Returns:
            Filtered list of elements (default: all elements)

        Example:
            >>> agent = SentienceAgent(browser, llm)
            >>> snap = snapshot(browser)
            >>> filtered = agent.filter_elements(snap, goal="Click login")
            >>> # filtered now contains only relevant elements
        """
        return snapshot.elements


class BaseAgentAsync(ABC):
    """
    Abstract base class for all async Sentience agents.

    Provides a standard interface for:
    - Executing natural language goals (act)
    - Tracking execution history
    - Monitoring token usage
    - Filtering elements based on goals

    Subclasses must implement:
    - act(): Execute a natural language goal (async)
    - get_history(): Return execution history
    - get_token_stats(): Return token usage statistics
    - clear_history(): Reset history and token counters

    Subclasses can override:
    - filter_elements(): Customize element filtering logic
    """

    @abstractmethod
    async def act(self, goal: str, **kwargs) -> AgentActionResult:
        """
        Execute a natural language goal using the agent (async).

        Args:
            goal: Natural language instruction (e.g., "Click the login button")
            **kwargs: Additional parameters (implementation-specific)

        Returns:
            AgentActionResult with execution details

        Raises:
            RuntimeError: If execution fails after retries
        """
        pass

    @abstractmethod
    def get_history(self) -> list[ActionHistory]:
        """
        Get the execution history of all actions taken.

        Returns:
            List of ActionHistory entries
        """
        pass

    @abstractmethod
    def get_token_stats(self) -> TokenStats:
        """
        Get token usage statistics for the agent session.

        Returns:
            TokenStats with cumulative token counts
        """
        pass

    @abstractmethod
    def clear_history(self) -> None:
        """
        Clear execution history and reset token counters.

        This resets the agent to a clean state.
        """
        pass

    def filter_elements(self, snapshot: Snapshot, goal: str | None = None) -> list[Element]:
        """
        Filter elements from a snapshot based on goal context.

        Default implementation returns all elements unchanged.
        Subclasses can override to implement custom filtering logic
        such as:
        - Removing irrelevant elements based on goal keywords
        - Boosting importance of matching elements
        - Filtering by role, size, or visual properties

        Args:
            snapshot: Current page snapshot
            goal: User's goal (can inform filtering strategy)

        Returns:
            Filtered list of elements (default: all elements)

        Example:
            >>> agent = SentienceAgentAsync(browser, llm)
            >>> snap = await snapshot_async(browser)
            >>> filtered = agent.filter_elements(snap, goal="Click login")
            >>> # filtered now contains only relevant elements
        """
        return snapshot.elements
