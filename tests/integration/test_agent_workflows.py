"""
Integration tests for SentienceAgent workflows.

Tests multi-step agent scenarios and error recovery without requiring real browser.
Uses mocks to simulate realistic browser behavior.
"""

from unittest.mock import Mock, patch

import pytest

from predicate.agent import SentienceAgent
from predicate.llm_provider import LLMProvider, LLMResponse
from predicate.models import BBox, Element, Snapshot, Viewport, VisualCues
from predicate.protocols import BrowserProtocol, PageProtocol


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for integration testing"""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.calls = []

    def generate(self, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, "kwargs": kwargs})

        if self.responses:
            response = self.responses[self.call_count % len(self.responses)]
        else:
            response = "CLICK(1)"

        self.call_count += 1

        return LLMResponse(
            content=response,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            model_name="mock-model",
        )

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return "mock-model"


class MockPage(PageProtocol):
    """Mock page that implements PageProtocol"""

    def __init__(self, url: str = "https://example.com"):
        self._url = url

    @property
    def url(self) -> str:
        return self._url

    def evaluate(self, script: str, *args, **kwargs):
        return {}

    def goto(self, url: str, **kwargs):
        self._url = url

    def wait_for_timeout(self, timeout: int):
        pass

    def wait_for_load_state(self, state: str = "load", timeout: int | None = None):
        pass

    def wait_for_function(self, expression: str, timeout: int | None = None):
        pass


class MockBrowser(BrowserProtocol):
    """Mock browser for integration testing"""

    def __init__(self):
        self._page = MockPage()
        self._started = False
        self.api_key = None  # Required by snapshot function
        self.api_url = None  # Required by snapshot function
        self._context = Mock()  # Mock context for storage state

    def start(self):
        self._started = True

    @property
    def page(self) -> PageProtocol | None:
        return self._page if self._started else None

    def goto(self, url: str):
        if self._page:
            self._page.goto(url)

    def close(self, output_path=None):
        self._started = False
        return output_path

    @property
    def context(self):
        return self._context


def create_mock_snapshot(elements=None):
    """Create a mock snapshot for testing"""
    if elements is None:
        elements = [
            Element(
                id=1,
                role="button",
                text="Click Me",
                importance=900,
                bbox=BBox(x=100, y=200, width=80, height=30),
                visual_cues=VisualCues(is_primary=True, is_clickable=True),
            ),
            Element(
                id=2,
                role="input",
                text="Search",
                importance=800,
                bbox=BBox(x=100, y=250, width=200, height=30),
                visual_cues=VisualCues(is_primary=False, is_clickable=True),
            ),
        ]
    return Snapshot(
        status="success",
        timestamp="2024-12-24T10:00:00Z",
        url="https://example.com",
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
    )


class TestAgentMultiStepWorkflows:
    """Test multi-step agent workflows"""

    def test_agent_multi_step_click_then_type(self):
        """Test agent performing multiple actions in sequence."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(2)", 'TYPE(2, "search query")'])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
            patch("predicate.action_executor.type_text") as mock_type,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )
            mock_type.return_value = ActionResult(
                success=True, duration_ms=200, outcome="dom_updated"
            )

            # First action: click input
            result1 = agent.act("Click the search input", max_retries=0)
            assert result1.success is True
            assert result1.action == "click"
            assert mock_click.call_count == 1

            # Second action: type into input
            result2 = agent.act("Type search query into the input", max_retries=0)
            assert result2.success is True
            assert result2.action == "type"
            assert mock_type.call_count == 1

            # Verify history tracks both actions
            assert len(agent.history) == 2

    def test_agent_workflow_with_retry(self):
        """Test agent workflow with retry on failure."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            # First call raises exception (triggers retry), second succeeds
            mock_click.side_effect = [
                RuntimeError("Element not found"),
                ActionResult(success=True, duration_ms=150, outcome="dom_updated"),
            ]

            result = agent.act("Click the button", max_retries=1)

            assert result.success is True
            assert mock_click.call_count == 2
            assert len(agent.history) == 1  # Only successful attempt recorded

    def test_agent_workflow_url_change(self):
        """Test agent workflow that causes URL change."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="navigated", url_changed=True
            )

            result = agent.act("Click the link", max_retries=0)

            assert result.success is True
            assert result.url_changed is True
            assert result.action == "click"

    def test_agent_workflow_finish_action(self):
        """Test agent workflow that finishes successfully."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["FINISH()"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with patch("predicate.agent.snapshot") as mock_snapshot:
            mock_snapshot.return_value = create_mock_snapshot()

            result = agent.act("Task is complete", max_retries=0)

            assert result.success is True
            assert result.action == "finish"
            assert len(agent.history) == 1

    def test_agent_workflow_token_tracking(self):
        """Test that token usage is tracked across workflow."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)", "CLICK(2)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )

            # Perform two actions
            agent.act("Click first button", max_retries=0)
            agent.act("Click second button", max_retries=0)

            # Check token stats
            stats = agent.get_token_stats()
            assert stats.total_tokens > 0
            assert stats.total_prompt_tokens > 0
            assert stats.total_completion_tokens > 0
            assert len(stats.by_action) == 2  # Two actions tracked


class TestAgentErrorRecovery:
    """Test agent error recovery scenarios"""

    def test_agent_recovery_after_snapshot_failure(self):
        """Test agent recovers after snapshot failure."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult, Snapshot

            # First snapshot fails, second succeeds
            failed_snapshot = Snapshot(
                status="error",
                error="Network timeout",
                url="https://example.com",
                viewport=Viewport(width=1920, height=1080),
                elements=[],
            )
            mock_snapshot.side_effect = [
                failed_snapshot,
                create_mock_snapshot(),
            ]
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )

            # Should raise on first attempt, succeed on retry
            with pytest.raises(RuntimeError, match="Snapshot failed"):
                agent.act("Click button", max_retries=0)

            # With retry, should succeed
            result = agent.act("Click button", max_retries=1)
            assert result.success is True

    def test_agent_recovery_after_action_failure(self):
        """Test agent recovers after action failure."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)", "CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            # First action fails, second succeeds
            mock_click.side_effect = [
                RuntimeError("Element not found"),
                ActionResult(success=True, duration_ms=150, outcome="dom_updated"),
            ]

            result = agent.act("Click button", max_retries=1)

            assert result.success is True
            assert mock_click.call_count == 2

    def test_agent_handles_max_retries_exceeded(self):
        """Test agent handles max retries exceeded."""
        browser = MockBrowser()
        browser.start()
        # Need multiple responses for multiple retries
        llm = MockLLMProvider(responses=["CLICK(1)", "CLICK(1)", "CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            # Raise exception to trigger retry logic (agent only retries on exceptions, not failed results)
            mock_click.side_effect = RuntimeError("Action failed")

            with pytest.raises(RuntimeError, match="Failed after"):
                agent.act("Click button", max_retries=2)

            # Should have attempted 3 times (initial + 2 retries)
            # Each attempt calls snapshot, LLM, and click
            assert mock_click.call_count == 3
            assert mock_snapshot.call_count >= 3
            assert llm.call_count >= 3


class TestAgentStateManagement:
    """Test agent state management across actions"""

    def test_agent_history_preservation(self):
        """Test that agent history is preserved across actions."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)", "CLICK(2)", "FINISH()"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )

            # Perform multiple actions
            agent.act("Click first", max_retries=0)
            agent.act("Click second", max_retries=0)
            agent.act("Finish", max_retries=0)

            # Verify history contains all actions
            assert len(agent.history) == 3
            assert agent.history[0]["goal"] == "Click first"
            assert agent.history[1]["goal"] == "Click second"
            assert agent.history[2]["goal"] == "Finish"

    def test_agent_step_count_increments(self):
        """Test that step count increments across actions."""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)", "CLICK(2)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("predicate.agent.snapshot") as mock_snapshot,
            patch("predicate.action_executor.click") as mock_click,
        ):
            from predicate.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )

            initial_count = agent._step_count

            agent.act("First action", max_retries=0)
            assert agent._step_count == initial_count + 1

            agent.act("Second action", max_retries=0)
            assert agent._step_count == initial_count + 2
