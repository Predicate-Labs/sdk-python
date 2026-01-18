from __future__ import annotations

import json

from sentience.failure_artifacts import (
    FailureArtifactBuffer,
    FailureArtifactsOptions,
    RedactionContext,
    RedactionResult,
)


def test_buffer_prunes_by_time(tmp_path) -> None:
    now = {"t": 0.0}

    def time_fn() -> float:
        return now["t"]

    opts = FailureArtifactsOptions(buffer_seconds=1.0, output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-1", options=opts, time_fn=time_fn)

    buf.add_frame(b"first")
    assert buf.frame_count() == 1

    now["t"] = 2.0
    buf.add_frame(b"second")
    assert buf.frame_count() == 1


def test_persist_writes_manifest_and_steps(tmp_path) -> None:
    now = {"t": 10.0}

    def time_fn() -> float:
        return now["t"]

    opts = FailureArtifactsOptions(output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-2", options=opts, time_fn=time_fn)

    buf.record_step(action="CLICK", step_id="s1", step_index=1, url="https://example.com")
    buf.add_frame(b"frame")

    snapshot = {
        "status": "success",
        "url": "https://example.com",
        "elements": [
            {"id": 1, "input_type": "password", "value": "secret"},
            {"id": 2, "input_type": "email", "value": "user@example.com"},
        ],
    }
    diagnostics = {"confidence": 0.9, "reasons": ["ok"], "metrics": {"quiet_ms": 42}}
    run_dir = buf.persist(
        reason="assert_failed",
        status="failure",
        snapshot=snapshot,
        diagnostics=diagnostics,
        metadata={"backend": "MockBackend", "url": "https://example.com"},
    )
    assert run_dir is not None
    manifest = json.loads((run_dir / "manifest.json").read_text())
    steps = json.loads((run_dir / "steps.json").read_text())
    snap_json = json.loads((run_dir / "snapshot.json").read_text())
    diag_json = json.loads((run_dir / "diagnostics.json").read_text())

    assert manifest["run_id"] == "run-2"
    assert manifest["frame_count"] == 1
    assert manifest["snapshot"] == "snapshot.json"
    assert manifest["diagnostics"] == "diagnostics.json"
    assert manifest["metadata"]["backend"] == "MockBackend"
    assert len(steps) == 1
    assert snap_json["url"] == "https://example.com"
    assert diag_json["confidence"] == 0.9
    assert snap_json["elements"][0]["value"] is None
    assert snap_json["elements"][0]["value_redacted"] is True
    assert snap_json["elements"][1]["value"] is None
    assert snap_json["elements"][1]["value_redacted"] is True


def test_redaction_callback_can_drop_frames(tmp_path) -> None:
    opts = FailureArtifactsOptions(output_dir=str(tmp_path))

    def redactor(ctx: RedactionContext) -> RedactionResult:
        return RedactionResult(drop_frames=True)

    opts.on_before_persist = redactor
    buf = FailureArtifactBuffer(run_id="run-3", options=opts)
    buf.add_frame(b"frame")

    run_dir = buf.persist(reason="fail", status="failure", snapshot={"status": "success"})
    assert run_dir is not None
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["frame_count"] == 0
    assert manifest["frames_dropped"] is True
