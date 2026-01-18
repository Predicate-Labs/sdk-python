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

    async def goto(self, url: str) -> None:
        self.page.url = url


class _Ctx:
    def __init__(self, deps):
        self.deps = deps


class _FakeTracer:
    def __init__(self):
        self.started_at = None
        self.calls = []

    def emit_run_start(self, agent, llm_model=None, config=None):
        # mimic Tracer behavior: set started_at so we don't re-emit
        self.started_at = object()
        self.calls.append(("run_start", {"agent": agent, "llm_model": llm_model, "config": config}))

    def emit_step_start(self, **kwargs):
        self.calls.append(("step_start", kwargs))

    def emit(self, event_type, data, step_id=None):
        self.calls.append((event_type, {"data": data, "step_id": step_id}))

    def emit_error(self, **kwargs):
        self.calls.append(("error", kwargs))


@pytest.mark.asyncio
async def test_register_sentience_tools_registers_expected_names():
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    expected = {
        "snapshot_state",
        "read_page",
        "click",
        "click_rect",
        "type_text",
        "press_key",
        "scroll_to",
        "navigate",
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


@pytest.mark.asyncio
async def test_tracing_emits_step_events_for_tool_calls():
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    tracer = _FakeTracer()
    deps = SentiencePydanticDeps(browser=_FakeAsyncBrowser(), tracer=tracer)  # type: ignore[arg-type]
    ctx = _Ctx(deps)

    _ = await tools["verify_url_matches"](ctx, r"example\.com")

    # We should emit run_start once, step_start once, step_end once
    types = [c[0] for c in tracer.calls]
    assert "run_start" in types
    assert "step_start" in types
    assert "step_end" in types


@pytest.mark.asyncio
async def test_navigate_sets_url_and_returns_success():
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    browser = _FakeAsyncBrowser()
    deps = SentiencePydanticDeps(browser=browser)  # type: ignore[arg-type]
    ctx = _Ctx(deps)

    out = await tools["navigate"](ctx, "https://example.com/next")
    assert out["success"] is True
    assert browser.page.url == "https://example.com/next"


@pytest.mark.asyncio
async def test_click_rect_is_registered(monkeypatch):
    agent = _FakeAgent()
    tools = register_sentience_tools(agent)

    called = {}

    async def _fake_click_rect_async(browser, rect, button="left", click_count=1, **kwargs):
        called["rect"] = rect
        called["button"] = button
        called["click_count"] = click_count
        return {"success": True}

    monkeypatch.setattr(
        "sentience.integrations.pydanticai.toolset.click_rect_async", _fake_click_rect_async
    )

    deps = SentiencePydanticDeps(browser=_FakeAsyncBrowser())  # type: ignore[arg-type]
    ctx = _Ctx(deps)

    out = await tools["click_rect"](
        ctx, x=10, y=20, width=30, height=40, button="left", click_count=2
    )
    assert out["success"] is True
    assert called["rect"] == {"x": 10, "y": 20, "w": 30, "h": 40}
    assert called["button"] == "left"
    assert called["click_count"] == 2
