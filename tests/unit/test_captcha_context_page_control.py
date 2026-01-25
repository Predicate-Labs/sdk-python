from __future__ import annotations

import pytest

from sentience.agent_runtime import AgentRuntime
from sentience.captcha import PageControlHook
from sentience.models import CaptchaDiagnostics, CaptchaEvidence, Snapshot, SnapshotDiagnostics


class EvalBackend:
    async def eval(self, code: str):
        _ = code
        return "ok"


class MockTracer:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.run_id = "test-run"

    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        self.events.append({"type": event_type, "data": data, "step_id": step_id})


def make_captcha_snapshot() -> Snapshot:
    evidence = CaptchaEvidence(
        iframe_src_hits=["https://www.google.com/recaptcha/api2/anchor"],
        text_hits=["captcha"],
        selector_hits=[],
        url_hits=[],
    )
    captcha = CaptchaDiagnostics(
        detected=True,
        provider_hint="recaptcha",
        confidence=0.9,
        evidence=evidence,
    )
    diagnostics = SnapshotDiagnostics(captcha=captcha)
    return Snapshot(
        status="success",
        url="https://example.com",
        elements=[],
        diagnostics=diagnostics,
    )


@pytest.mark.asyncio
async def test_captcha_context_page_control_evaluate_js() -> None:
    runtime = AgentRuntime(backend=EvalBackend(), tracer=MockTracer())
    runtime.begin_step("captcha_test")

    ctx = runtime._build_captcha_context(make_captcha_snapshot(), source="gateway")
    assert isinstance(ctx.page_control, PageControlHook)

    result = await ctx.page_control.evaluate_js("1+1")
    assert result == "ok"
