from __future__ import annotations

from predicate.agent_runtime import AgentRuntime
from predicate.integrations.authority import (
    AuthorityActionInput,
    build_action_request_from_runtime,
    to_verification_evidence,
)
from predicate.models import Snapshot


class _MockBackend:
    async def get_url(self) -> str:
        return "https://example.com"


class _MockTracer:
    # pylint: disable=unused-argument
    def emit(self, event_type: str, data: dict, step_id: str | None = None) -> None:
        return


class _RuntimeStub:
    def __init__(self) -> None:
        self.step_id = "step-7"
        self.last_snapshot = Snapshot(
            status="success",
            url="https://example.com/checkout",
            timestamp="2026-02-17T00:00:00Z",
            elements=[],
        )

    def get_assertions_for_step_end(self) -> dict[str, object]:
        return {
            "assertions": [
                {"label": "on_checkout", "passed": True, "required": True, "reason": ""},
                {"label": "has_total", "passed": False, "required": True, "reason": "selector_missing"},
            ]
        }


def test_to_verification_evidence_maps_assertions() -> None:
    evidence = to_verification_evidence(
        [
            {"label": "a", "passed": True, "required": True, "reason": ""},
            {"label": "b", "passed": False, "required": False, "reason": "missing"},
        ]
    )
    assert len(evidence.signals) == 2
    assert evidence.signals[0].label == "a"
    assert evidence.signals[0].status.value == "passed"
    assert evidence.signals[1].label == "b"
    assert evidence.signals[1].status.value == "failed"
    assert evidence.signals[1].reason == "missing"


def test_build_action_request_from_runtime_exports_contracts() -> None:
    runtime = _RuntimeStub()
    request = build_action_request_from_runtime(
        runtime=runtime,
        action_input=AuthorityActionInput(
            principal_id="agent:checkout",
            action="http.post",
            resource="https://api.vendor.com/orders",
            intent="submit order",
            tenant_id="tenant-a",
            session_id="session-1",
        ),
    )
    assert request.principal.principal_id == "agent:checkout"
    assert request.action_spec.intent == "submit order"
    assert request.state_evidence.source == "sdk-python"
    assert request.state_evidence.state_hash.startswith("sha256:")
    assert len(request.verification_evidence.signals) == 2


def test_agent_runtime_build_authority_action_request() -> None:
    runtime = AgentRuntime(backend=_MockBackend(), tracer=_MockTracer())
    runtime.step_id = "step-1"
    runtime.last_snapshot = Snapshot(
        status="success",
        url="https://example.com",
        timestamp="2026-02-17T00:00:00Z",
        elements=[],
    )
    runtime._assertions_this_step = [  # pylint: disable=protected-access
        {"label": "has_heading", "passed": True, "required": True, "reason": ""}
    ]
    request = runtime.build_authority_action_request(
        principal_id="agent:web",
        action="browser.click",
        resource="https://example.com",
        intent="click checkout",
    )
    assert request.principal.principal_id == "agent:web"
    assert request.action_spec.action == "browser.click"
    assert request.state_evidence.state_hash.startswith("sha256:")
    assert request.verification_evidence.signals[0].label == "has_heading"
