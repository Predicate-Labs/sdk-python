from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# pylint: disable=import-error

from predicate_contracts import (
    ActionRequest,
    ActionSpec,
    PrincipalRef,
    StateEvidence,
    VerificationEvidence,
    VerificationSignal,
    VerificationStatus,
)


@dataclass(frozen=True)
class AuthorityActionInput:
    principal_id: str
    action: str
    resource: str
    intent: str
    tenant_id: str | None = None
    session_id: str | None = None
    state_source: str = "sdk-python"


def to_verification_evidence(assertions: Sequence[Mapping[str, Any]]) -> VerificationEvidence:
    signals: list[VerificationSignal] = []
    for assertion in assertions:
        label = str(assertion.get("label", "")).strip()
        if label == "":
            continue
        passed = bool(assertion.get("passed", False))
        required = bool(assertion.get("required", False))
        reason_raw = assertion.get("reason")
        reason = str(reason_raw) if isinstance(reason_raw, str) and reason_raw != "" else None
        signals.append(
            VerificationSignal(
                label=label,
                status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
                required=required,
                reason=reason,
            )
        )
    return VerificationEvidence(signals=tuple(signals))


def state_evidence_from_runtime(runtime: Any, source: str = "sdk-python") -> StateEvidence:
    snapshot = getattr(runtime, "last_snapshot", None)
    step_id = getattr(runtime, "step_id", None)
    state_hash = _snapshot_state_hash(snapshot=snapshot, step_id=step_id)
    return StateEvidence(source=source, state_hash=state_hash)


def build_action_request_from_runtime(runtime: Any, action_input: AuthorityActionInput) -> ActionRequest:
    assertions_payload = runtime.get_assertions_for_step_end()
    assertions = assertions_payload.get("assertions", [])
    verification_evidence = to_verification_evidence(assertions)
    state_evidence = state_evidence_from_runtime(runtime=runtime, source=action_input.state_source)
    return ActionRequest(
        principal=PrincipalRef(
            principal_id=action_input.principal_id,
            tenant_id=action_input.tenant_id,
            session_id=action_input.session_id,
        ),
        action_spec=ActionSpec(
            action=action_input.action,
            resource=action_input.resource,
            intent=action_input.intent,
        ),
        state_evidence=state_evidence,
        verification_evidence=verification_evidence,
    )


def _snapshot_state_hash(snapshot: Any, step_id: str | None) -> str:
    url = str(getattr(snapshot, "url", "") or "")
    timestamp = str(getattr(snapshot, "timestamp", "") or "")
    if url != "" or timestamp != "":
        digest = hashlib.sha256(f"{url}{timestamp}".encode("utf-8")).hexdigest()
        return "sha256:" + digest
    fallback_material = step_id or "missing_snapshot"
    fallback_digest = hashlib.sha256(fallback_material.encode("utf-8")).hexdigest()
    return "sha256:" + fallback_digest
