"""
Unit tests for Sentience Agent Layer (Phase 1)
Tests LLM providers and SentienceAgent without requiring browser
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sentience.llm_provider import LLMProvider, LLMResponse, OpenAIProvider, AnthropicProvider
from sentience.agent import SentienceAgent
from sentience.models import Snapshot, Element, BBox, VisualCues, Viewport


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing"""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.calls = []

    def generate(self, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append({
            "system": system_prompt,
            "user": user_prompt,
            "kwargs": kwargs
        })

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
            model_name="mock-model"
        )

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return "mock-model"


# ========== LLM Provider Tests ==========

def test_llm_response_dataclass():
    """Test LLMResponse dataclass creation"""
    response = LLMResponse(
        content="CLICK(42)",
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        model_name="gpt-4o"
    )

    assert response.content == "CLICK(42)"
    assert response.prompt_tokens == 100
    assert response.completion_tokens == 20
    assert response.total_tokens == 120
    assert response.model_name == "gpt-4o"


def test_mock_llm_provider():
    """Test mock LLM provider"""
    provider = MockLLMProvider(responses=["CLICK(1)", "TYPE(2, \"test\")"])

    # First call
    response1 = provider.generate("system", "user")
    assert response1.content == "CLICK(1)"
    assert provider.call_count == 1

    # Second call
    response2 = provider.generate("system", "user")
    assert response2.content == "TYPE(2, \"test\")"
    assert provider.call_count == 2

    # Check calls were recorded
    assert len(provider.calls) == 2
    assert provider.calls[0]["system"] == "system"


@pytest.mark.skipif(True, reason="Requires openai package and API key")
def test_openai_provider_init():
    """Test OpenAI provider initialization (skipped without API key)"""
    provider = OpenAIProvider(api_key="test-key", model="gpt-4o")
    assert provider.model_name == "gpt-4o"
    assert provider.supports_json_mode() is True


@pytest.mark.skipif(True, reason="Requires anthropic package and API key")
def test_anthropic_provider_init():
    """Test Anthropic provider initialization (skipped without API key)"""
    provider = AnthropicProvider(api_key="test-key", model="claude-3-sonnet")
    assert provider.model_name == "claude-3-sonnet"
    assert provider.supports_json_mode() is False


# ========== SentienceAgent Tests ==========

def create_mock_browser():
    """Create mock browser for testing"""
    browser = Mock()
    browser.page = Mock()
    browser.page.url = "https://example.com"
    return browser


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
                is_primary=True,
                is_clickable=True,
                background_color_name="blue"
            ),
            in_viewport=True,
            is_occluded=False,
            z_index=10
        ),
        Element(
            id=2,
            role="textbox",
            text="",
            importance=850,
            bbox=BBox(x=100, y=100, width=200, height=40),
            visual_cues=VisualCues(
                is_primary=False,
                is_clickable=True,
                background_color_name=None
            ),
            in_viewport=True,
            is_occluded=False,
            z_index=5
        )
    ]

    return Snapshot(
        status="success",
        timestamp="2024-12-24T10:00:00Z",
        url="https://example.com",
        viewport=Viewport(width=1920, height=1080),
        elements=elements
    )


def test_agent_initialization():
    """Test SentienceAgent initialization"""
    browser = create_mock_browser()
    llm = MockLLMProvider()

    agent = SentienceAgent(browser, llm, snapshot_limit=50, verbose=False)

    assert agent.browser == browser
    assert agent.llm == llm
    assert agent.snapshot_limit == 50
    assert agent.verbose is False
    assert len(agent.history) == 0
    assert agent.token_usage["total_tokens"] == 0


def test_agent_build_context():
    """Test context building from snapshot"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()
    context = agent._build_context(snap, "test goal")

    # Should contain both elements
    assert "[1]" in context
    assert "[2]" in context
    assert "button" in context
    assert "textbox" in context
    assert "Click Me" in context
    assert "PRIMARY" in context
    assert "CLICKABLE" in context
    assert "color:blue" in context
    assert "(Imp:900)" in context


def test_agent_execute_click_action():
    """Test parsing and executing CLICK action"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()

    # Mock click function
    with patch('sentience.agent.click') as mock_click:
        from sentience.models import ActionResult
        mock_click.return_value = ActionResult(
            success=True,
            duration_ms=150,
            outcome="dom_updated",
            url_changed=False
        )

        result = agent._execute_action("CLICK(1)", snap)

        assert result["success"] is True
        assert result["action"] == "click"
        assert result["element_id"] == 1
        mock_click.assert_called_once_with(browser, 1)


def test_agent_execute_type_action():
    """Test parsing and executing TYPE action"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()

    # Mock type_text function
    with patch('sentience.agent.type_text') as mock_type:
        from sentience.models import ActionResult
        mock_type.return_value = ActionResult(
            success=True,
            duration_ms=200,
            outcome="dom_updated"
        )

        result = agent._execute_action('TYPE(2, "hello world")', snap)

        assert result["success"] is True
        assert result["action"] == "type"
        assert result["element_id"] == 2
        assert result["text"] == "hello world"
        mock_type.assert_called_once_with(browser, 2, "hello world")


def test_agent_execute_press_action():
    """Test parsing and executing PRESS action"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()

    # Mock press function
    with patch('sentience.agent.press') as mock_press:
        from sentience.models import ActionResult
        mock_press.return_value = ActionResult(
            success=True,
            duration_ms=50,
            outcome="dom_updated"
        )

        result = agent._execute_action('PRESS("Enter")', snap)

        assert result["success"] is True
        assert result["action"] == "press"
        assert result["key"] == "Enter"
        mock_press.assert_called_once_with(browser, "Enter")


def test_agent_execute_finish_action():
    """Test parsing FINISH action"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()
    result = agent._execute_action("FINISH()", snap)

    assert result["success"] is True
    assert result["action"] == "finish"


def test_agent_execute_invalid_action():
    """Test handling of invalid action format"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()

    with pytest.raises(ValueError, match="Unknown action format"):
        agent._execute_action("INVALID_ACTION", snap)


def test_agent_act_full_cycle():
    """Test full act() cycle with mocked dependencies"""
    browser = create_mock_browser()
    llm = MockLLMProvider(responses=["CLICK(1)"])
    agent = SentienceAgent(browser, llm, verbose=False)

    # Mock snapshot and click
    with patch('sentience.agent.snapshot') as mock_snapshot, \
         patch('sentience.agent.click') as mock_click:

        from sentience.models import ActionResult
        mock_snapshot.return_value = create_mock_snapshot()
        mock_click.return_value = ActionResult(
            success=True,
            duration_ms=150,
            outcome="dom_updated"
        )

        result = agent.act("Click the button", max_retries=0)

        assert result["success"] is True
        assert result["action"] == "click"
        assert result["element_id"] == 1
        assert result["goal"] == "Click the button"

        # Check history was recorded
        assert len(agent.history) == 1
        assert agent.history[0]["goal"] == "Click the button"

        # Check tokens were tracked
        assert agent.token_usage["total_tokens"] > 0


def test_agent_token_tracking():
    """Test token usage tracking"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    # Simulate multiple actions
    response1 = LLMResponse(content="CLICK(1)", prompt_tokens=100, completion_tokens=20, total_tokens=120)
    response2 = LLMResponse(content="TYPE(2, \"test\")", prompt_tokens=150, completion_tokens=30, total_tokens=180)

    agent._track_tokens("goal 1", response1)
    agent._track_tokens("goal 2", response2)

    stats = agent.get_token_stats()
    assert stats["total_prompt_tokens"] == 250
    assert stats["total_completion_tokens"] == 50
    assert stats["total_tokens"] == 300
    assert len(stats["by_action"]) == 2


def test_agent_clear_history():
    """Test clearing history and token stats"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    # Add some history
    agent.history.append({"goal": "test"})
    agent.token_usage["total_tokens"] = 100

    agent.clear_history()

    assert len(agent.history) == 0
    assert agent.token_usage["total_tokens"] == 0


def test_agent_retry_on_failure():
    """Test retry logic on action failure"""
    browser = create_mock_browser()
    llm = MockLLMProvider(responses=["CLICK(999)"])  # Invalid element ID
    agent = SentienceAgent(browser, llm, verbose=False)

    # Mock snapshot and click (click will fail)
    with patch('sentience.agent.snapshot') as mock_snapshot, \
         patch('sentience.agent.click') as mock_click:

        mock_snapshot.return_value = create_mock_snapshot()
        # Simulate click failure
        mock_click.side_effect = RuntimeError("Element not found")

        with pytest.raises(RuntimeError, match="Failed after 2 retries"):
            agent.act("Click invalid element", max_retries=2)

        # Should have attempted 3 times (initial + 2 retries)
        assert mock_click.call_count == 3


def test_agent_action_parsing_variations():
    """Test various action string format variations"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = SentienceAgent(browser, llm, verbose=False)

    snap = create_mock_snapshot()

    with patch('sentience.agent.click') as mock_click, \
         patch('sentience.agent.type_text') as mock_type, \
         patch('sentience.agent.press') as mock_press:

        from sentience.models import ActionResult
        mock_result = ActionResult(success=True, duration_ms=100, outcome="dom_updated")
        mock_click.return_value = mock_result
        mock_type.return_value = mock_result
        mock_press.return_value = mock_result

        # Test variations
        agent._execute_action("click(1)", snap)  # lowercase
        agent._execute_action("CLICK( 1 )", snap)  # extra spaces
        agent._execute_action("TYPE(2, 'single quotes')", snap)  # single quotes
        agent._execute_action("PRESS('Enter')", snap)  # single quotes
        agent._execute_action("finish()", snap)  # lowercase finish

        assert mock_click.call_count == 2
        assert mock_type.call_count == 1
        assert mock_press.call_count == 1
