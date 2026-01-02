"""
Integration tests for ConversationalAgent (Phase 2)
Tests natural language interface without requiring browser
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from sentience.conversational_agent import ConversationalAgent
from sentience.llm_provider import LLMProvider, LLMResponse
from sentience.models import BBox, Element, Snapshot, Viewport, VisualCues


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing conversational agent"""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_count = 0
        self.calls = []

    def generate(self, system_prompt: str, user_prompt: str, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, "kwargs": kwargs})

        # Determine response based on content
        if "planning assistant" in system_prompt.lower():
            # Return plan
            response = self.responses.get("plan", self._default_plan())
        elif "extract" in system_prompt.lower():
            # Return extraction result
            response = self.responses.get(
                "extract", '{"found": true, "data": {}, "summary": "Info extracted"}'
            )
        elif "verify" in system_prompt.lower():
            # Return verification result
            response = self.responses.get(
                "verify", '{"verified": true, "reasoning": "Condition met"}'
            )
        elif "summarize" in system_prompt.lower():
            # Return summary
            response = self.responses.get("summary", "Task completed successfully")
        else:
            # Default technical agent response
            response = self.responses.get("action", "CLICK(1)")

        self.call_count += 1

        return LLMResponse(
            content=response,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            model_name="mock-model",
        )

    def _default_plan(self):
        return json.dumps(
            {
                "intent": "Test intent",
                "steps": [
                    {
                        "action": "NAVIGATE",
                        "description": "Go to test.com",
                        "parameters": {"url": "https://test.com"},
                    }
                ],
                "expected_outcome": "Success",
            }
        )

    def supports_json_mode(self) -> bool:
        return True

    @property
    def model_name(self) -> str:
        return "mock-model"


def create_mock_browser():
    """Create mock browser for testing"""
    browser = Mock()
    browser.page = Mock()
    browser.page.url = "https://test.com"
    browser.page.goto = Mock()
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
                is_primary=True, is_clickable=True, background_color_name="blue"
            ),
            in_viewport=True,
            is_occluded=False,
            z_index=10,
        )
    ]

    return Snapshot(
        status="success",
        timestamp="2024-12-24T10:00:00Z",
        url="https://test.com",
        viewport=Viewport(width=1920, height=1080),
        elements=elements,
    )


# ========== ConversationalAgent Tests ==========


def test_conversational_agent_initialization():
    """Test ConversationalAgent initialization"""
    browser = create_mock_browser()
    llm = MockLLMProvider()

    agent = ConversationalAgent(browser, llm, verbose=False)

    assert agent.browser == browser
    assert agent.llm == llm
    assert agent.verbose is False
    assert len(agent.conversation_history) == 0
    assert agent.technical_agent is not None


def test_create_plan():
    """Test plan creation from natural language"""
    browser = create_mock_browser()

    plan_json = json.dumps(
        {
            "intent": "Search for magic mouse",
            "steps": [
                {
                    "action": "NAVIGATE",
                    "description": "Go to google.com",
                    "parameters": {"url": "https://google.com"},
                },
                {
                    "action": "FIND_AND_CLICK",
                    "description": "Click search box",
                    "parameters": {"element_description": "search box"},
                },
            ],
            "expected_outcome": "Search initiated",
        }
    )

    llm = MockLLMProvider(responses={"plan": plan_json})
    agent = ConversationalAgent(browser, llm, verbose=False)

    plan = agent._create_plan("Search for magic mouse on google")

    assert plan["intent"] == "Search for magic mouse"
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["action"] == "NAVIGATE"
    assert plan["steps"][1]["action"] == "FIND_AND_CLICK"


def test_create_plan_json_fallback():
    """Test plan creation with invalid JSON fallback"""
    browser = create_mock_browser()
    llm = MockLLMProvider(responses={"plan": "INVALID JSON{"})
    agent = ConversationalAgent(browser, llm, verbose=False)

    plan = agent._create_plan("Click button")

    # Should fall back to simple plan
    assert "intent" in plan
    assert "steps" in plan
    assert len(plan["steps"]) > 0


def test_execute_navigate_step():
    """Test NAVIGATE step execution"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = ConversationalAgent(browser, llm, verbose=False)

    step = {
        "action": "NAVIGATE",
        "description": "Go to google.com",
        "parameters": {"url": "google.com"},  # Without https://
    }

    result = agent._execute_step(step)

    assert result.success is True
    assert result.action == "NAVIGATE"
    browser.page.goto.assert_called_once()
    # Should have added https://
    assert "https://google.com" in str(browser.page.goto.call_args)


def test_execute_find_and_click_step():
    """Test FIND_AND_CLICK step execution"""
    browser = create_mock_browser()
    llm = MockLLMProvider(responses={"action": "CLICK(1)"})
    agent = ConversationalAgent(browser, llm, verbose=False)

    step = {
        "action": "FIND_AND_CLICK",
        "description": "Click the button",
        "parameters": {"element_description": "button"},
    }

    # Patch at the agent module level where it's imported
    with (
        patch("sentience.agent.snapshot") as mock_snapshot,
        patch("sentience.agent.click") as mock_click,
    ):
        from sentience.models import ActionResult

        mock_snapshot.return_value = create_mock_snapshot()
        mock_click.return_value = ActionResult(success=True, duration_ms=150, outcome="dom_updated")

        result = agent._execute_step(step)

        assert result.action == "FIND_AND_CLICK"
        # Technical agent should have been called
        assert len(agent.technical_agent.history) > 0


def test_execute_find_and_type_step():
    """Test FIND_AND_TYPE step execution"""
    browser = create_mock_browser()
    llm = MockLLMProvider(responses={"action": 'TYPE(1, "test")'})
    agent = ConversationalAgent(browser, llm, verbose=False)

    step = {
        "action": "FIND_AND_TYPE",
        "description": "Type into search box",
        "parameters": {"element_description": "search box", "text": "magic mouse"},
    }

    # Patch at the agent module level where it's imported
    with (
        patch("sentience.agent.snapshot") as mock_snapshot,
        patch("sentience.agent.type_text") as mock_type,
    ):
        from sentience.models import ActionResult

        mock_snapshot.return_value = create_mock_snapshot()
        mock_type.return_value = ActionResult(success=True, duration_ms=200, outcome="dom_updated")

        result = agent._execute_step(step)

        assert result.action == "FIND_AND_TYPE"
        assert result.data["text"] == "magic mouse"


def test_execute_wait_step():
    """Test WAIT step execution"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = ConversationalAgent(browser, llm, verbose=False)

    step = {
        "action": "WAIT",
        "description": "Wait for page to load",
        "parameters": {"duration": 0.1},  # Short wait for testing
    }

    result = agent._execute_step(step)

    assert result.success is True
    assert result.action == "WAIT"
    assert result.data["duration"] == 0.1


def test_execute_extract_info_step():
    """Test EXTRACT_INFO step execution"""
    browser = create_mock_browser()

    extract_response = json.dumps(
        {"found": True, "data": {"price": "$79"}, "summary": "Found price information"}
    )

    llm = MockLLMProvider(responses={"extract": extract_response})
    agent = ConversationalAgent(browser, llm, verbose=False)

    step = {
        "action": "EXTRACT_INFO",
        "description": "Extract price",
        "parameters": {"info_type": "product price"},
    }

    with patch("sentience.conversational_agent.snapshot") as mock_snapshot:
        mock_snapshot.return_value = create_mock_snapshot()

        result = agent._execute_step(step)

        assert result.success is True
        assert result.action == "EXTRACT_INFO"
        extracted = result.data["extracted"]
        if isinstance(extracted, dict):
            assert extracted["found"] is True
        else:
            assert extracted.found is True


def test_execute_verify_step():
    """Test VERIFY step execution"""
    browser = create_mock_browser()

    verify_response = json.dumps({"verified": True, "reasoning": "Page contains results"})

    llm = MockLLMProvider(responses={"verify": verify_response})
    agent = ConversationalAgent(browser, llm, verbose=False)

    step = {
        "action": "VERIFY",
        "description": "Verify results",
        "parameters": {"condition": "page contains search results"},
    }

    with patch("sentience.conversational_agent.snapshot") as mock_snapshot:
        mock_snapshot.return_value = create_mock_snapshot()

        result = agent._execute_step(step)

        assert result.success is True
        assert result.action == "VERIFY"
        assert result.data["verified"] is True


def test_synthesize_response():
    """Test natural language response synthesis"""
    browser = create_mock_browser()

    llm = MockLLMProvider(
        responses={
            "summary": "I navigated to google.com and found the search results you requested."
        }
    )

    agent = ConversationalAgent(browser, llm, verbose=False)

    plan = {
        "intent": "Search for magic mouse",
        "steps": [],
        "expected_outcome": "Success",
    }

    execution_results = [{"success": True, "action": "NAVIGATE"}]

    response = agent._synthesize_response("Search for magic mouse", plan, execution_results)

    assert isinstance(response, str)
    assert len(response) > 0


def test_execute_full_workflow():
    """Test full execute() workflow"""
    browser = create_mock_browser()

    plan_json = json.dumps(
        {
            "intent": "Navigate to test site",
            "steps": [
                {
                    "action": "NAVIGATE",
                    "description": "Go to test.com",
                    "parameters": {"url": "https://test.com"},
                }
            ],
            "expected_outcome": "Navigation complete",
        }
    )

    llm = MockLLMProvider(
        responses={"plan": plan_json, "summary": "Successfully navigated to test.com"}
    )

    agent = ConversationalAgent(browser, llm, verbose=False)

    response = agent.execute("Go to test.com")

    assert isinstance(response, str)
    assert len(agent.conversation_history) == 1
    assert agent.conversation_history[0]["user_input"] == "Go to test.com"


def test_chat_method():
    """Test chat() method as alias for execute()"""
    browser = create_mock_browser()

    plan_json = json.dumps({"intent": "Test", "steps": [], "expected_outcome": "Done"})

    llm = MockLLMProvider(responses={"plan": plan_json, "summary": "Task complete"})

    agent = ConversationalAgent(browser, llm, verbose=False)

    response = agent.chat("Test message")

    assert isinstance(response, str)
    assert len(agent.conversation_history) == 1


def test_get_summary():
    """Test session summary generation"""
    browser = create_mock_browser()

    llm = MockLLMProvider(
        responses={
            "plan": '{"intent": "test", "steps": [], "expected_outcome": "done"}',
            "summary": "Session completed with 2 interactions",
        }
    )

    agent = ConversationalAgent(browser, llm, verbose=False)

    # Add some history
    agent.conversation_history.append({"user_input": "Test 1", "response": "Done 1"})
    agent.conversation_history.append({"user_input": "Test 2", "response": "Done 2"})

    summary = agent.get_summary()

    assert isinstance(summary, str)
    assert len(summary) > 0


def test_get_summary_empty_history():
    """Test summary with no history"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = ConversationalAgent(browser, llm, verbose=False)

    summary = agent.get_summary()

    assert summary == "No actions have been performed yet."


def test_clear_history():
    """Test clearing conversation history"""
    browser = create_mock_browser()
    llm = MockLLMProvider()
    agent = ConversationalAgent(browser, llm, verbose=False)

    # Add history
    agent.conversation_history.append({"test": "data"})
    agent.technical_agent.history.append({"test": "data"})

    agent.clear_history()

    assert len(agent.conversation_history) == 0
    assert len(agent.technical_agent.history) == 0
