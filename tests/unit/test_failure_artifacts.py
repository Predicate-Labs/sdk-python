from __future__ import annotations

import json
from unittest.mock import patch

from sentience.failure_artifacts import (
    ClipOptions,
    FailureArtifactBuffer,
    FailureArtifactsOptions,
    RedactionContext,
    RedactionResult,
    _is_ffmpeg_available,
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


# -------------------- Phase 4: Clip generation tests --------------------


def test_clip_mode_off_skips_generation(tmp_path) -> None:
    """When clip.mode='off', no clip generation is attempted."""
    opts = FailureArtifactsOptions(
        output_dir=str(tmp_path),
        clip=ClipOptions(mode="off"),
    )
    buf = FailureArtifactBuffer(run_id="run-clip-off", options=opts)
    buf.add_frame(b"frame")

    run_dir = buf.persist(reason="fail", status="failure")
    assert run_dir is not None
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["clip"] is None
    assert manifest["clip_fps"] is None


def test_clip_mode_auto_skips_when_ffmpeg_missing(tmp_path) -> None:
    """When clip.mode='auto' and ffmpeg is not available, skip silently."""
    with patch("sentience.failure_artifacts._is_ffmpeg_available", return_value=False):
        opts = FailureArtifactsOptions(
            output_dir=str(tmp_path),
            clip=ClipOptions(mode="auto", fps=10),
        )
        buf = FailureArtifactBuffer(run_id="run-clip-auto", options=opts)
        buf.add_frame(b"frame")

        run_dir = buf.persist(reason="fail", status="failure")
        assert run_dir is not None
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["clip"] is None
        assert manifest["clip_fps"] is None


def test_clip_mode_on_warns_when_ffmpeg_missing(tmp_path) -> None:
    """When clip.mode='on' and ffmpeg is not available, log warning but don't fail."""
    with patch("sentience.failure_artifacts._is_ffmpeg_available", return_value=False):
        opts = FailureArtifactsOptions(
            output_dir=str(tmp_path),
            clip=ClipOptions(mode="on"),
        )
        buf = FailureArtifactBuffer(run_id="run-clip-on-missing", options=opts)
        buf.add_frame(b"frame")

        run_dir = buf.persist(reason="fail", status="failure")
        assert run_dir is not None
        manifest = json.loads((run_dir / "manifest.json").read_text())
        # Should not have clip since ffmpeg is not available
        assert manifest["clip"] is None


def test_clip_generation_with_mock_ffmpeg(tmp_path) -> None:
    """Test clip generation logic with mocked ffmpeg subprocess."""
    with patch("sentience.failure_artifacts._is_ffmpeg_available", return_value=True):
        with patch("sentience.failure_artifacts._generate_clip_from_frames") as mock_gen:
            mock_gen.return_value = True  # Simulate successful clip generation

            opts = FailureArtifactsOptions(
                output_dir=str(tmp_path),
                clip=ClipOptions(mode="on", fps=12),
            )
            buf = FailureArtifactBuffer(run_id="run-clip-mock", options=opts)
            buf.add_frame(b"frame1")
            buf.add_frame(b"frame2")

            run_dir = buf.persist(reason="fail", status="failure")
            assert run_dir is not None

            # Verify _generate_clip_from_frames was called with correct args
            assert mock_gen.called
            call_args = mock_gen.call_args
            assert call_args.kwargs["fps"] == 12

            manifest = json.loads((run_dir / "manifest.json").read_text())
            assert manifest["clip"] == "failure.mp4"
            assert manifest["clip_fps"] == 12


def test_clip_not_generated_when_frames_dropped(tmp_path) -> None:
    """Clip should not be generated when frames are dropped by redaction."""
    with patch("sentience.failure_artifacts._is_ffmpeg_available", return_value=True):
        with patch("sentience.failure_artifacts._generate_clip_from_frames") as mock_gen:
            opts = FailureArtifactsOptions(
                output_dir=str(tmp_path),
                clip=ClipOptions(mode="on"),
                on_before_persist=lambda ctx: RedactionResult(drop_frames=True),
            )
            buf = FailureArtifactBuffer(run_id="run-clip-dropped", options=opts)
            buf.add_frame(b"frame")

            run_dir = buf.persist(reason="fail", status="failure")
            assert run_dir is not None

            # Should not call clip generation when frames are dropped
            assert not mock_gen.called
            manifest = json.loads((run_dir / "manifest.json").read_text())
            assert manifest["clip"] is None
            assert manifest["frames_dropped"] is True


def test_is_ffmpeg_available_with_missing_binary() -> None:
    """Test _is_ffmpeg_available returns False when ffmpeg is not found."""
    with patch("sentience.failure_artifacts.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")
        assert _is_ffmpeg_available() is False


def test_is_ffmpeg_available_with_timeout() -> None:
    """Test _is_ffmpeg_available returns False on timeout."""
    import subprocess

    with patch("sentience.failure_artifacts.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=5)
        assert _is_ffmpeg_available() is False


# -------------------- Phase 5: Cloud upload tests --------------------


def test_upload_to_cloud_returns_none_when_no_artifacts_dir(tmp_path) -> None:
    """upload_to_cloud returns None when artifacts directory doesn't exist."""
    opts = FailureArtifactsOptions(output_dir=str(tmp_path / "nonexistent"))
    buf = FailureArtifactBuffer(run_id="run-upload-1", options=opts)

    result = buf.upload_to_cloud(api_key="test-key")
    assert result is None


def test_upload_to_cloud_returns_none_when_no_manifest(tmp_path) -> None:
    """upload_to_cloud returns None when manifest.json is missing."""
    # Create a directory but no manifest
    run_dir = tmp_path / "run-upload-2-123"
    run_dir.mkdir(parents=True)

    opts = FailureArtifactsOptions(output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-upload-2", options=opts)

    result = buf.upload_to_cloud(api_key="test-key", persisted_dir=run_dir)
    assert result is None


def test_collect_artifacts_for_upload(tmp_path) -> None:
    """Test that _collect_artifacts_for_upload collects correct files."""
    opts = FailureArtifactsOptions(output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-collect", options=opts)
    buf.add_frame(b"frame1")

    run_dir = buf.persist(
        reason="fail",
        status="failure",
        snapshot={"status": "success"},
        diagnostics={"confidence": 0.9},
    )
    assert run_dir is not None

    # Read manifest
    manifest = json.loads((run_dir / "manifest.json").read_text())

    # Collect artifacts
    artifacts = buf._collect_artifacts_for_upload(run_dir, manifest)

    # Should have: manifest.json, steps.json, snapshot.json, diagnostics.json, and 1 frame
    artifact_names = [a["name"] for a in artifacts]
    assert "manifest.json" in artifact_names
    assert "steps.json" in artifact_names
    assert "snapshot.json" in artifact_names
    assert "diagnostics.json" in artifact_names
    assert any(a.startswith("frames/") for a in artifact_names)

    # Verify all files exist
    for artifact in artifacts:
        assert artifact["path"].exists()
        assert artifact["size_bytes"] > 0
        assert artifact["content_type"] in ["application/json", "image/png", "image/jpeg"]


def test_upload_to_cloud_with_mocked_gateway(tmp_path) -> None:
    """Test full upload flow with mocked HTTP requests."""
    from unittest.mock import MagicMock

    opts = FailureArtifactsOptions(output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-mock-upload", options=opts)
    buf.add_frame(b"frame1")

    run_dir = buf.persist(
        reason="fail",
        status="failure",
        snapshot={"status": "success"},
    )
    assert run_dir is not None

    # Mock the HTTP requests
    mock_response_init = MagicMock()
    mock_response_init.status_code = 200
    mock_response_init.json.return_value = {
        "upload_urls": [
            {
                "name": "manifest.json",
                "upload_url": "https://mock.com/manifest",
                "storage_key": "test/manifest.json",
            },
            {
                "name": "steps.json",
                "upload_url": "https://mock.com/steps",
                "storage_key": "test/steps.json",
            },
            {
                "name": "snapshot.json",
                "upload_url": "https://mock.com/snapshot",
                "storage_key": "test/snapshot.json",
            },
        ],
        "artifact_index_upload": {
            "upload_url": "https://mock.com/index",
            "storage_key": "test/index.json",
        },
    }

    mock_response_upload = MagicMock()
    mock_response_upload.status_code = 200

    mock_response_complete = MagicMock()
    mock_response_complete.status_code = 200

    with patch("sentience.failure_artifacts.requests.post") as mock_post:
        with patch("sentience.failure_artifacts.requests.put") as mock_put:
            mock_post.side_effect = [mock_response_init, mock_response_complete]
            mock_put.return_value = mock_response_upload

            result = buf.upload_to_cloud(api_key="test-key", persisted_dir=run_dir)

            # Should return artifact index key
            assert result == "test/index.json"

            # Verify POST calls were made
            assert mock_post.call_count == 2

            # Verify PUT calls were made for each artifact + index
            assert mock_put.call_count >= 3  # At least manifest, steps, snapshot


def test_upload_to_cloud_handles_gateway_error(tmp_path) -> None:
    """Test that upload_to_cloud handles gateway errors gracefully."""
    from unittest.mock import MagicMock

    opts = FailureArtifactsOptions(output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-error", options=opts)
    buf.add_frame(b"frame1")

    run_dir = buf.persist(reason="fail", status="failure")
    assert run_dir is not None

    # Mock gateway returning error
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("sentience.failure_artifacts.requests.post") as mock_post:
        mock_post.return_value = mock_response

        result = buf.upload_to_cloud(api_key="test-key", persisted_dir=run_dir)
        assert result is None


def test_upload_to_cloud_handles_network_error(tmp_path) -> None:
    """Test that upload_to_cloud handles network errors gracefully."""
    import requests

    opts = FailureArtifactsOptions(output_dir=str(tmp_path))
    buf = FailureArtifactBuffer(run_id="run-network-error", options=opts)
    buf.add_frame(b"frame1")

    run_dir = buf.persist(reason="fail", status="failure")
    assert run_dir is not None

    with patch("sentience.failure_artifacts.requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

        result = buf.upload_to_cloud(api_key="test-key", persisted_dir=run_dir)
        assert result is None
