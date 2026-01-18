import types

import pytest

from sentience.integrations.pydanticai.deps import SentiencePydanticDeps
from sentience.integrations.pydanticai.toolset import register_sentience_tools
from sentience.models import BBox, Element, Snapshot


class _FakeAgent:
    def __init__(self):
        self._tools = {}

    def tool(self, fn):
        # PydanticAI's decorator registers the function for tool calling.
        # For unit tests we just store it by name and return it unchanged.
        self._tools[fn.__name__] = fn
        return fn


class _FakeAsyncPage:
    url = "https://example.com/"


class _FakeAsyncBrowser:
    def __init__(self):
        self.page = _FakeAsyncPage()
        self.api_key = None
        self.api_url = None


class _Ctx:
    def __init__(self, deps):
        self.deps = deps


@pytest.mark.asyncio
async def test_register_sentience_tools_registers_expected_names():
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    expected = {
        "snapshot_state",
        "read_page",
        "click",
        "type_text",
        "press_key",
        "find_text_rect",
        "verify_url_matches",
        "verify_text_present",
        "assert_eventually_url_matches",
    }
    assert set(tools.keys()) == expected
    assert set(agent._tools.keys()) == expected


@pytest.mark.asyncio
async def test_snapshot_state_passes_limit_and_summarizes(monkeypatch):
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    captured = {}

    async def _fake_snapshot_async(browser, options):
        captured["limit"] = options.limit
        captured["screenshot"] = options.screenshot
        return Snapshot(
            status="success",
            url="https://example.com/",
            elements=[
                Element(
                    id=1,
                    role="button",
                    text="Sign in",
                    importance=10,
                    bbox=BBox(x=1, y=2, width=3, height=4),
                    visual_cues={
                        "is_primary": False,
                        "is_clickable": True,
                        "background_color_name": None,
                    },
                )
            ],
        )

    monkeypatch.setattr(
        "sentience.integrations.pydanticai.toolset.snapshot_async", _fake_snapshot_async
    )

    deps = SentiencePydanticDeps(browser=_FakeAsyncBrowser())  # type: ignore[arg-type]
    ctx = _Ctx(deps)

    result = await tools["snapshot_state"](ctx, limit=10, include_screenshot=False)
    assert captured["limit"] == 10
    assert captured["screenshot"] is False
    assert result.url == "https://example.com/"
    assert len(result.elements) == 1
    assert result.elements[0].id == 1
    assert result.elements[0].role == "button"


@pytest.mark.asyncio
async def test_verify_url_matches_uses_page_url():
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    deps = SentiencePydanticDeps(browser=_FakeAsyncBrowser())  # type: ignore[arg-type]
    ctx = _Ctx(deps)

    ok = await tools["verify_url_matches"](ctx, r"example\.com")
    bad = await tools["verify_url_matches"](ctx, r"not-real")

    assert ok.passed is True
    assert bad.passed is False

