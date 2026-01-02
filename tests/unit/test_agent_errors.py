"""
Unit tests for agent error handling and edge cases.

These tests use mocked browsers to test error conditions that are
difficult to reproduce with real browsers.
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from sentience.agent import SentienceAgent
from sentience.llm_provider import LLMProvider, LLMResponse
from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues
from sentience.protocols import BrowserProtocol, PageProtocol


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing"""

    def __init__(self, responses=None):
        super().__init__("mock-model")
        self.responses = responses or []
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-model"

    def supports_json_mode(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_prompt: str, **kwargs):
        self.call_count += 1
        if self.responses:
            response = self.responses[self.call_count % len(self.responses)]
        else:
            response = "CLICK(1)"
        return LLMResponse(
            content=response,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            model_name="mock-model",
        )


class MockPage(PageProtocol):
    """Mock page that implements PageProtocol (sync version)"""

    def __init__(self, url: str = "https://example.com"):
        self._url = url

    @property
    def url(self) -> str:
        return self._url

    def evaluate(self, script: str, *args: Any, **kwargs: Any) -> Any:
        # Return proper snapshot structure when snapshot is called
        # The script is a function that calls window.sentience.snapshot(options)
        if "window.sentience.snapshot" in script or (
            "snapshot" in script.lower() and "options" in script
        ):
            # Check if args contain options (for empty snapshot tests)
            options = kwargs.get("options") or (args[0] if args else {})
            limit = options.get("limit", 50) if isinstance(options, dict) else 50

            # Return elements based on limit (0 for empty snapshot tests)
            elements = []
            if limit > 0:
                elements = [
                    {
                        "id": 1,
                        "role": "button",
                        "text": "Click Me",
                        "importance": 900,
                        "bbox": {"x": 100, "y": 200, "width": 80, "height": 30},
                        "visual_cues": {
                            "is_primary": True,
                            "is_clickable": True,
                            "background_color_name": "blue",
                        },
                        "in_viewport": True,
                        "is_occluded": False,
                        "z_index": 10,
                    }
                ]

            # Snapshot model expects 'elements' not 'raw_elements'
            return {
                "status": "success",
                "timestamp": "2024-12-24T10:00:00Z",
                "url": self._url,
                "viewport": {"width": 1920, "height": 1080},
                "elements": elements,  # Use 'elements' for Snapshot model
                "raw_elements": elements,  # Also include for compatibility
            }
        # For wait_for_function calls
        if "wait_for_function" in script or "typeof window.sentience" in script:
            return True
        return {}

    def goto(self, url: str, **kwargs: Any) -> Any:
        self._url = url
        return None

    def wait_for_timeout(self, timeout: int) -> None:
        pass

    def wait_for_load_state(self, state: str = "load", timeout: int | None = None) -> None:
        pass

    def wait_for_function(self, expression: str, timeout: int | None = None) -> None:
        """Add wait_for_function to make it detectable as sync page"""
        pass


class MockBrowser(BrowserProtocol):
    """Mock browser that implements BrowserProtocol"""

    def __init__(self, page: MockPage | None = None, api_key: str | None = None):
        self._page = page or MockPage()
        self._started = False
        self.api_key = api_key  # Required by snapshot function
        self.api_url = None  # Required by snapshot function

    @property
    def page(self) -> MockPage | None:
        return self._page if self._started else None

    def start(self) -> None:
        self._started = True

    def close(self, output_path: str | None = None) -> str | None:
        self._started = False
        return output_path

    def goto(self, url: str) -> None:
        if self._page:
            self._page.goto(url)


def create_mock_snapshot():
    """Create mock snapshot with test elements"""
    elements = [
        Element(
            id=1,
            role="button",
            text="Click Me",
            importance=900,
            bbox=BBox(x=100, y=200, width=80, height=30),
            visual_cues=VisualCues(
                is_primary=True, is_clickable=True, background_color_name="blue"
            ),
            in_viewport=True,
            is_occluded=False,
            z_index=10,
        ),
    ]
    return Snapshot(
        status="success",
        timestamp="2024-12-24T10:00:00Z",
        url="https://example.com",
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
    )


class TestAgentErrorHandling:
    """Test agent error handling scenarios"""

    def test_agent_handles_snapshot_timeout(self):
        """Test agent handles snapshot timeout gracefully"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider()
        agent = SentienceAgent(browser, llm, verbose=False)

        # Mock snapshot to raise timeout
        with patch("sentience.agent.snapshot") as mock_snapshot:
            from playwright._impl._errors import TimeoutError

            mock_snapshot.side_effect = TimeoutError("Snapshot timeout")

            with pytest.raises(RuntimeError, match="Failed after"):
                agent.act("Click the button", max_retries=0)

    def test_agent_handles_network_failure(self):
        """Test agent handles network failure during snapshot"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider()
        agent = SentienceAgent(browser, llm, verbose=False)

        # Mock snapshot to raise network error
        with patch("sentience.snapshot.snapshot") as mock_snapshot:
            mock_snapshot.side_effect = ConnectionError("Network failure")

            with pytest.raises(RuntimeError, match="Failed after"):
                agent.act("Click the button", max_retries=0)

    def test_agent_handles_empty_snapshot(self):
        """Test agent handles empty snapshot (no elements)"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        # Create empty snapshot
        empty_snap = Snapshot(
            status="success",
            timestamp="2024-12-24T10:00:00Z",
            url="https://example.com",
            viewport=Viewport(width=1920, height=1080),
            elements=[],
        )

        with (
            patch("sentience.agent.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = empty_snap
            mock_click.return_value = ActionResult(
                success=False, duration_ms=100, outcome="Element not found"
            )

            # Agent should still attempt action even with empty snapshot
            result = agent.act("Click the button", max_retries=0)
            assert result.success is False

    def test_agent_handles_malformed_llm_response(self):
        """Test agent handles malformed LLM response"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["INVALID_RESPONSE_FORMAT"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (patch("sentience.snapshot.snapshot") as mock_snapshot,):
            mock_snapshot.return_value = create_mock_snapshot()

            # Action executor should raise ValueError for invalid format
            with pytest.raises(RuntimeError, match="Failed after"):
                agent.act("Click the button", max_retries=0)

    def test_agent_handles_browser_not_started(self):
        """Test agent handles browser not started error"""
        browser = MockBrowser()  # Not started
        llm = MockLLMProvider()
        agent = SentienceAgent(browser, llm, verbose=False)

        # Snapshot should fail because browser.page is None
        with patch("sentience.snapshot.snapshot") as mock_snapshot:
            mock_snapshot.side_effect = RuntimeError("Browser not started")

            with pytest.raises(RuntimeError, match="Failed after"):
                agent.act("Click the button", max_retries=0)

    def test_agent_handles_action_timeout(self):
        """Test agent handles action execution timeout"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from playwright._impl._errors import TimeoutError

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.side_effect = TimeoutError("Action timeout")

            with pytest.raises(RuntimeError, match="Failed after"):
                agent.act("Click the button", max_retries=0)

    def test_agent_handles_url_change_during_action(self):
        """Test agent handles URL change during action execution"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            # Simulate URL change after click
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="navigated", url_changed=True
            )

            result = agent.act("Click the button", max_retries=0)
            assert result.success is True
            assert result.url_changed is True

    def test_agent_retry_on_transient_error(self):
        """Test agent retries on transient errors"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            # First call fails, second succeeds
            mock_click.side_effect = [
                RuntimeError("Transient error"),
                ActionResult(success=True, duration_ms=150, outcome="dom_updated"),
            ]

            result = agent.act("Click the button", max_retries=1)
            assert result.success is True
            assert mock_click.call_count == 2


class TestAgentEdgeCases:
    """Test agent edge case scenarios"""

    def test_agent_handles_zero_elements_in_snapshot(self):
        """Test agent handles snapshot with zero elements"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["FINISH()"])
        agent = SentienceAgent(browser, llm, verbose=False)

        empty_snap = Snapshot(
            status="success",
            timestamp="2024-12-24T10:00:00Z",
            url="https://example.com",
            viewport=Viewport(width=1920, height=1080),
            elements=[],
        )

        with patch("sentience.snapshot.snapshot") as mock_snapshot:
            mock_snapshot.return_value = empty_snap

            # Agent should handle empty snapshot and finish
            result = agent.act("Complete task", max_retries=0)
            assert result.action == "finish"
            assert result.success is True

    def test_agent_handles_unicode_in_actions(self):
        """Test agent handles unicode characters in goals and actions"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=['TYPE(1, "你好世界")'])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.type_text") as mock_type,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_type.return_value = ActionResult(
                success=True, duration_ms=200, outcome="dom_updated"
            )

            result = agent.act("Type 你好世界", max_retries=0)
            assert result.success is True
            assert result.action == "type"

    def test_agent_handles_special_characters_in_goal(self):
        """Test agent handles special characters in goal text"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )

            # Test with special characters
            result = agent.act('Click the "Submit" button (with quotes)', max_retries=0)
            assert result.success is True

    def test_agent_preserves_state_on_retry(self):
        """Test agent preserves state correctly during retries"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        agent = SentienceAgent(browser, llm, verbose=False)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            # First attempt fails, second succeeds
            mock_click.side_effect = [
                RuntimeError("First attempt failed"),
                ActionResult(success=True, duration_ms=150, outcome="dom_updated"),
            ]

            result = agent.act("Click the button", max_retries=1)
            assert result.success is True
            # History should have both attempts
            assert len(agent.history) == 1  # Only successful attempt is recorded
            assert agent.history[0]["attempt"] == 1  # Final successful attempt

    def test_agent_handles_tracer_errors_gracefully(self):
        """Test agent continues execution even if tracer fails"""
        browser = MockBrowser()
        browser.start()
        llm = MockLLMProvider(responses=["CLICK(1)"])
        # Create a tracer that raises errors
        mock_tracer = Mock()
        mock_tracer.emit.side_effect = RuntimeError("Tracer error")

        agent = SentienceAgent(browser, llm, verbose=False, tracer=mock_tracer)

        with (
            patch("sentience.snapshot.snapshot") as mock_snapshot,
            patch("sentience.action_executor.click") as mock_click,
        ):
            from sentience.models import ActionResult

            mock_snapshot.return_value = create_mock_snapshot()
            mock_click.return_value = ActionResult(
                success=True, duration_ms=150, outcome="dom_updated"
            )

            # Agent should still complete action despite tracer error
            result = agent.act("Click the button", max_retries=0)
            assert result.success is True
