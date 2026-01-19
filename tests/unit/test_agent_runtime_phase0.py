from __future__ import annotations

from unittest.mock import MagicMock

from sentience.agent_runtime import AgentRuntime
from sentience.models import BBox, Element, VisualCues
from sentience.verification import is_disabled, is_enabled, value_equals


class MockBackend:
    """Mock BrowserBackend implementation for unit tests."""

    async def get_url(self) -> str:
        return "https://example.com"

    async def refresh_page_info(self):
        return None


class MockTracer:
    """Mock Tracer for unit tests."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        self.events.append(
            {
                "type": event_type,
                "data": data,
                "step_id": step_id,
            }
        )


def test_assert_state_predicates_use_snapshot_context() -> None:
    """State-aware predicates should run against snapshot context."""
    backend = MockBackend()
    tracer = MockTracer()
    runtime = AgentRuntime(backend=backend, tracer=tracer)
    runtime.begin_step(goal="Test")

    cues = VisualCues(is_primary=False, background_color_name=None, is_clickable=True)
    elements = [
        Element(
            id=1,
            role="button",
            text="Submit",
            importance=10,
            bbox=BBox(x=0, y=0, width=100, height=40),
            visual_cues=cues,
            disabled=False,
        ),
        Element(
            id=2,
            role="textbox",
            text=None,
            importance=5,
            bbox=BBox(x=0, y=50, width=200, height=40),
            visual_cues=cues,
            value="hello",
            input_type="text",
            disabled=False,
        ),
        Element(
            id=3,
            role="button",
            text="Disabled",
            importance=4,
            bbox=BBox(x=0, y=100, width=120, height=40),
            visual_cues=cues,
            disabled=True,
        ),
    ]

    runtime.last_snapshot = MagicMock(url="https://example.com", elements=elements)

    assert runtime.assert_(is_enabled("text~'Submit'"), label="enabled") is True
    assert runtime.assert_(is_disabled("text~'Disabled'"), label="disabled") is True
    assert runtime.assert_(value_equals("role=textbox", "hello"), label="value") is True
    assert len(runtime._assertions_this_step) == 3
