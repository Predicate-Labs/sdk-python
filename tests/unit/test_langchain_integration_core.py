import pytest

from sentience.integrations.langchain.context import SentienceLangChainContext
from sentience.integrations.langchain.core import SentienceLangChainCore
from sentience.models import BBox, Element, Snapshot


class _FakeAsyncPage:
    url = "https://example.com/"


class _FakeAsyncBrowser:
    def __init__(self):
        self.page = _FakeAsyncPage()
        self.api_key = None
        self.api_url = None

    async def goto(self, url: str) -> None:
        self.page.url = url


class _FakeTracer:
    def __init__(self):
        self.started_at = None
        self.calls = []

    def emit_run_start(self, agent, llm_model=None, config=None):
        self.started_at = object()
        self.calls.append(("run_start", {"agent": agent, "config": config}))

    def emit_step_start(self, **kwargs):
        self.calls.append(("step_start", kwargs))

    def emit(self, event_type, data, step_id=None):
        self.calls.append((event_type, {"step_id": step_id, "data": data}))

    def emit_error(self, **kwargs):
        self.calls.append(("error", kwargs))


@pytest.mark.asyncio
async def test_core_verify_url_matches_and_tracing():
    tracer = _FakeTracer()
    ctx = SentienceLangChainContext(browser=_FakeAsyncBrowser(), tracer=tracer)  # type: ignore[arg-type]
    core = SentienceLangChainCore(ctx)

    ok = await core.verify_url_matches(r"example\.com")
    assert ok.passed is True

    types = [c[0] for c in tracer.calls]
    assert "run_start" in types
    assert "step_start" in types
    assert "step_end" in types


@pytest.mark.asyncio
async def test_core_navigate_updates_url():
    ctx = SentienceLangChainContext(browser=_FakeAsyncBrowser())  # type: ignore[arg-type]
    core = SentienceLangChainCore(ctx)

    out = await core.navigate("https://example.com/next")
    assert out["success"] is True
    assert ctx.browser.page.url == "https://example.com/next"


@pytest.mark.asyncio
async def test_core_snapshot_state_summarizes(monkeypatch):
    async def _fake_snapshot_async(browser, options):
        assert options.limit == 10
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
        "sentience.integrations.langchain.core.snapshot_async", _fake_snapshot_async
    )

    ctx = SentienceLangChainContext(browser=_FakeAsyncBrowser())  # type: ignore[arg-type]
    core = SentienceLangChainCore(ctx)

    state = await core.snapshot_state(limit=10, include_screenshot=False)
    assert state.url == "https://example.com/"
    assert len(state.elements) == 1
    assert state.elements[0].id == 1
