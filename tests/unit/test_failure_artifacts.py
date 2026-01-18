from __future__ import annotations

import json

from sentience.failure_artifacts import FailureArtifactBuffer, FailureArtifactsOptions


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

    run_dir = buf.persist(reason="assert_failed", status="failure")
    assert run_dir is not None
    manifest = json.loads((run_dir / "manifest.json").read_text())
    steps = json.loads((run_dir / "steps.json").read_text())

    assert manifest["run_id"] == "run-2"
    assert manifest["frame_count"] == 1
    assert len(steps) == 1
