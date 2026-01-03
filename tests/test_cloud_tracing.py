"""Tests for sentience.cloud_tracing module"""

import base64
import gzip
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from sentience.cloud_tracing import CloudTraceSink
from sentience.tracer_factory import create_tracer
from sentience.tracing import JsonlTraceSink, Tracer


class TestCloudTraceSink:
    """Test CloudTraceSink functionality."""

    def test_cloud_trace_sink_upload_success(self):
        """Test CloudTraceSink successfully uploads trace to cloud."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-run-123"

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Success"
            mock_put.return_value = mock_response

            # Create sink and emit events
            sink = CloudTraceSink(upload_url, run_id=run_id)
            sink.emit({"v": 1, "type": "run_start", "seq": 1, "data": {"agent": "TestAgent"}})
            sink.emit({"v": 1, "type": "run_end", "seq": 2, "data": {"steps": 1}})

            # Close triggers upload
            sink.close()

            # Verify request was made
            assert mock_put.called
            assert mock_put.call_count == 1

            # Verify URL and headers
            call_args = mock_put.call_args
            assert call_args[0][0] == upload_url
            assert call_args[1]["headers"]["Content-Type"] == "application/x-gzip"
            assert call_args[1]["headers"]["Content-Encoding"] == "gzip"

            # Verify body is gzip compressed
            uploaded_data = call_args[1]["data"]
            decompressed = gzip.decompress(uploaded_data)
            lines = decompressed.decode("utf-8").strip().split("\n")

            assert len(lines) == 2
            event1 = json.loads(lines[0])
            event2 = json.loads(lines[1])

            assert event1["type"] == "run_start"
            assert event2["type"] == "run_end"

            # Verify file was deleted on successful upload
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            assert not trace_path.exists(), "Trace file should be deleted after successful upload"

    def test_cloud_trace_sink_upload_failure_preserves_trace(self, capsys):
        """Test CloudTraceSink preserves trace locally on upload failure."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-run-456"

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            # Mock failed response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_put.return_value = mock_response

            # Create sink and emit events
            sink = CloudTraceSink(upload_url, run_id=run_id)
            sink.emit({"v": 1, "type": "run_start", "seq": 1})

            # Close triggers upload (which will fail)
            sink.close()

            # Verify error message printed
            captured = capsys.readouterr()
            assert "❌" in captured.out
            assert "Upload failed: HTTP 500" in captured.out
            assert "Local trace preserved" in captured.out

            # Verify file was preserved on failure
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            assert trace_path.exists(), "Trace file should be preserved on upload failure"

            # Cleanup
            if trace_path.exists():
                os.remove(trace_path)

    def test_cloud_trace_sink_emit_after_close_raises(self):
        """Test CloudTraceSink raises error when emitting after close."""
        upload_url = "https://test.com/upload"
        sink = CloudTraceSink(upload_url, run_id="test-run-789")
        # Emit at least one event so file exists
        sink.emit({"v": 1, "type": "test", "seq": 1})
        sink.close()

        with pytest.raises(RuntimeError, match="CloudTraceSink is closed"):
            sink.emit({"v": 1, "type": "test", "seq": 2})

    def test_cloud_trace_sink_context_manager(self):
        """Test CloudTraceSink works as context manager."""
        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)

            upload_url = "https://test.com/upload"
            with CloudTraceSink(upload_url, run_id="test-run-context") as sink:
                sink.emit({"v": 1, "type": "test", "seq": 1})

            # Verify upload was called
            assert mock_put.called

    def test_cloud_trace_sink_network_error_graceful_degradation(self, capsys):
        """Test CloudTraceSink handles network errors gracefully."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-run-network-error"

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            # Simulate network error
            mock_put.side_effect = Exception("Network error")

            sink = CloudTraceSink(upload_url, run_id=run_id)
            sink.emit({"v": 1, "type": "test", "seq": 1})

            # Ensure file is written before close
            sink._trace_file.flush()
            sink._trace_file.close()

            # Should not raise, just print warning
            sink.close()

            captured = capsys.readouterr()
            assert "❌" in captured.out or "Error uploading trace" in captured.out

            # Verify file was preserved
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            # File should exist if emit was called (even if close fails)
            if trace_path.exists():
                # Cleanup
                os.remove(trace_path)

    def test_cloud_trace_sink_multiple_close_safe(self):
        """Test CloudTraceSink.close() is idempotent."""
        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)

            upload_url = "https://test.com/upload"
            sink = CloudTraceSink(upload_url, run_id="test-run-multiple-close")
            sink.emit({"v": 1, "type": "test", "seq": 1})

            # Close multiple times
            sink.close()
            sink.close()
            sink.close()

            # Upload should only be called once
            assert mock_put.call_count == 1

    def test_cloud_trace_sink_persistent_cache_directory(self):
        """Test CloudTraceSink uses persistent cache directory instead of temp file."""
        upload_url = "https://test.com/upload"
        run_id = "test-run-persistent"

        sink = CloudTraceSink(upload_url, run_id=run_id)
        sink.emit({"v": 1, "type": "test", "seq": 1})

        # Verify file is in persistent cache directory
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        assert trace_path.exists(), "Trace file should be in persistent cache directory"
        assert cache_dir.exists(), "Cache directory should exist"

        # Cleanup
        sink.close()
        if trace_path.exists():
            os.remove(trace_path)

    def test_cloud_trace_sink_non_blocking_close(self):
        """Test CloudTraceSink.close(blocking=False) returns immediately."""
        upload_url = "https://test.com/upload"
        run_id = "test-run-nonblocking"

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)

            sink = CloudTraceSink(upload_url, run_id=run_id)
            sink.emit({"v": 1, "type": "test", "seq": 1})

            # Non-blocking close should return immediately
            start_time = time.time()
            sink.close(blocking=False)
            elapsed = time.time() - start_time

            # Should return in < 0.1 seconds (much faster than upload)
            assert elapsed < 0.1, "Non-blocking close should return immediately"

            # Wait a bit for background thread to complete
            time.sleep(0.5)

            # Verify upload was called
            assert mock_put.called

    def test_cloud_trace_sink_progress_callback(self):
        """Test CloudTraceSink.close() with progress callback."""
        upload_url = "https://test.com/upload"
        run_id = "test-run-progress"
        progress_calls = []

        def progress_callback(uploaded: int, total: int):
            progress_calls.append((uploaded, total))

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)

            sink = CloudTraceSink(upload_url, run_id=run_id)
            sink.emit({"v": 1, "type": "test", "seq": 1})

            sink.close(blocking=True, on_progress=progress_callback)

            # Verify progress callback was called
            assert len(progress_calls) > 0, "Progress callback should be called"
            # Last call should have uploaded == total
            assert progress_calls[-1][0] == progress_calls[-1][1], "Final progress should be 100%"

    def test_cloud_trace_sink_uploads_screenshots_after_trace(self):
        """Test that CloudTraceSink uploads screenshots after trace upload succeeds."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-integration-1"
        api_key = "sk_test_123"

        # Create test screenshot
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        # Emit trace event with screenshot embedded
        sink.emit(
            {
                "v": 1,
                "type": "snapshot",
                "ts": "2026-01-01T00:00:00.000Z",
                "run_id": run_id,
                "seq": 1,
                "step_id": "step-1",
                "data": {
                    "url": "https://example.com",
                    "element_count": 10,
                    "screenshot_base64": test_image_base64,
                    "screenshot_format": "png",
                },
            }
        )

        # Mock all HTTP calls
        mock_upload_urls = {
            "1": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0001.png?signature=...",
        }

        with (
            patch("sentience.cloud_tracing.requests.put") as mock_put,
            patch("sentience.cloud_tracing.requests.post") as mock_post,
        ):
            # Mock trace upload (first PUT)
            mock_trace_response = Mock()
            mock_trace_response.status_code = 200
            mock_put.return_value = mock_trace_response

            # Mock screenshot init (first POST)
            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {"upload_urls": mock_upload_urls}

            # Mock screenshot upload (second PUT)
            mock_screenshot_response = Mock()
            mock_screenshot_response.status_code = 200

            # Mock complete (second POST)
            mock_complete_response = Mock()
            mock_complete_response.status_code = 200

            # Setup mock to return different responses for different calls
            def put_side_effect(*args, **kwargs):
                url = args[0] if args else kwargs.get("url", "")
                if "screenshots" in url:
                    return mock_screenshot_response
                return mock_trace_response

            def post_side_effect(*args, **kwargs):
                url = args[0] if args else kwargs.get("url", "")
                if "screenshots/init" in url:
                    return mock_init_response
                return mock_complete_response

            mock_put.side_effect = put_side_effect
            mock_post.side_effect = post_side_effect

            # Close triggers upload (which extracts screenshots and uploads them)
            sink.close()

            # Verify trace was uploaded
            assert mock_put.call_count >= 1

            # Verify screenshot init was called
            post_calls = [call[0][0] for call in mock_post.call_args_list]
            assert any("screenshots/init" in url for url in post_calls)

            # Verify screenshot was uploaded (second PUT call)
            put_urls = [call[0][0] for call in mock_put.call_args_list]
            assert any("screenshots" in url for url in put_urls)

            # Verify uploaded trace data does NOT contain screenshot_base64
            trace_upload_call = None
            for call in mock_put.call_args_list:
                headers = call[1].get("headers", {})
                if headers.get("Content-Type") == "application/x-gzip":
                    trace_upload_call = call
                    break

            assert trace_upload_call is not None, "Trace upload should have been called"

            # Verify completion request includes all required stats fields
            complete_calls = [call for call in mock_post.call_args_list if "complete" in call[0][0]]
            assert len(complete_calls) > 0, "Completion request should have been called"

            complete_call = complete_calls[0]
            complete_data = complete_call[1].get("json", {})
            stats = complete_data.get("stats", {})

            # Verify all required fields are present
            assert "trace_file_size_bytes" in stats
            assert "screenshot_total_size_bytes" in stats
            assert "screenshot_count" in stats
            assert "index_file_size_bytes" in stats
            assert "total_steps" in stats
            assert "total_events" in stats
            assert "duration_ms" in stats
            assert "final_status" in stats
            assert "started_at" in stats
            assert "ended_at" in stats

            # Decompress and verify screenshot_base64 is removed
            compressed_data = trace_upload_call[1]["data"]
            decompressed_data = gzip.decompress(compressed_data)
            trace_content = decompressed_data.decode("utf-8")
            events = [
                json.loads(line) for line in trace_content.strip().split("\n") if line.strip()
            ]

            snapshot_events = [e for e in events if e.get("type") == "snapshot"]
            assert len(snapshot_events) > 0, "Should have snapshot event"

            for event in snapshot_events:
                data = event.get("data", {})
                assert (
                    "screenshot_base64" not in data
                ), "screenshot_base64 should be removed from uploaded trace"
                assert (
                    "screenshot_format" not in data
                ), "screenshot_format should be removed from uploaded trace"

        # Cleanup
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        cleaned_trace_path = cache_dir / f"{run_id}.cleaned.jsonl"
        if trace_path.exists():
            os.remove(trace_path)
        if cleaned_trace_path.exists():
            os.remove(cleaned_trace_path)


class TestTracerFactory:
    """Test create_tracer factory function."""

    def test_create_tracer_pro_tier_success(self, capsys):
        """Test create_tracer returns CloudTraceSink for Pro tier."""
        with patch("sentience.tracer_factory.requests.post") as mock_post:
            with patch("sentience.cloud_tracing.requests.put") as mock_put:
                # Mock API response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "upload_url": "https://sentience.nyc3.digitaloceanspaces.com/upload"
                }
                mock_post.return_value = mock_response

                # Mock upload response
                mock_put.return_value = Mock(status_code=200)

                tracer = create_tracer(
                    api_key="sk_pro_test123", run_id="test-run", upload_trace=True
                )

                # Verify Pro tier message
                captured = capsys.readouterr()
                assert "☁️  [Sentience] Cloud tracing enabled (Pro tier)" in captured.out

                # Verify tracer works
                assert tracer.run_id == "test-run"
                # Check if sink is CloudTraceSink (it should be)
                from sentience.cloud_tracing import CloudTraceSink

                assert isinstance(
                    tracer.sink, CloudTraceSink
                ), f"Expected CloudTraceSink, got {type(tracer.sink)}"
                assert tracer.sink.run_id == "test-run"  # Verify run_id is passed

                # Verify the init API was called
                assert mock_post.called
                assert mock_post.call_count == 1

                # Cleanup - emit at least one event so file exists before close
                tracer.emit("test", {"v": 1, "seq": 1})
                tracer.close()

    def test_create_tracer_free_tier_fallback(self, capsys):
        """Test create_tracer falls back to local for free tier."""
        with tempfile.TemporaryDirectory():
            tracer = create_tracer(run_id="test-run")

            # Verify local tracing message
            captured = capsys.readouterr()
            assert "💾 [Sentience] Local tracing:" in captured.out
            # Use os.path.join for platform-independent path checking
            import os

            expected_path = os.path.join("traces", "test-run.jsonl")
            assert expected_path in captured.out

            # Verify tracer works
            assert tracer.run_id == "test-run"
            assert isinstance(tracer.sink, JsonlTraceSink)

            # Cleanup
            tracer.close()

    def test_create_tracer_api_forbidden_fallback(self, capsys):
        """Test create_tracer falls back when API returns 403 Forbidden."""
        with patch("sentience.tracer_factory.requests.post") as mock_post:
            # Mock API response with 403
            mock_response = Mock()
            mock_response.status_code = 403
            mock_post.return_value = mock_response

            with tempfile.TemporaryDirectory():
                tracer = create_tracer(
                    api_key="sk_free_test123", run_id="test-run", upload_trace=True
                )

                # Verify warning message
                captured = capsys.readouterr()
                assert "⚠️  [Sentience] Cloud tracing requires Pro tier" in captured.out
                assert "Falling back to local-only tracing" in captured.out

                # Verify fallback to local
                assert isinstance(tracer.sink, JsonlTraceSink)

                tracer.close()

    def test_create_tracer_api_timeout_fallback(self, capsys):
        """Test create_tracer falls back on timeout."""
        import requests

        with patch("sentience.tracer_factory.requests.post") as mock_post:
            # Mock timeout
            mock_post.side_effect = requests.exceptions.Timeout("Connection timeout")

            with tempfile.TemporaryDirectory():
                tracer = create_tracer(api_key="sk_test123", run_id="test-run", upload_trace=True)

                # Verify warning message
                captured = capsys.readouterr()
                assert "⚠️  [Sentience] Cloud init timeout" in captured.out
                assert "Falling back to local-only tracing" in captured.out

                # Verify fallback to local
                assert isinstance(tracer.sink, JsonlTraceSink)

                tracer.close()

    def test_create_tracer_api_connection_error_fallback(self, capsys):
        """Test create_tracer falls back on connection error."""
        import requests

        with patch("sentience.tracer_factory.requests.post") as mock_post:
            # Mock connection error
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

            with tempfile.TemporaryDirectory():
                tracer = create_tracer(api_key="sk_test123", run_id="test-run", upload_trace=True)

                # Verify warning message
                captured = capsys.readouterr()
                assert "⚠️  [Sentience] Cloud init connection error" in captured.out

                # Verify fallback to local
                assert isinstance(tracer.sink, JsonlTraceSink)

                tracer.close()

    def test_create_tracer_generates_run_id_if_not_provided(self):
        """Test create_tracer generates UUID if run_id not provided."""
        with tempfile.TemporaryDirectory():
            tracer = create_tracer()

            # Verify run_id was generated
            assert tracer.run_id is not None
            assert len(tracer.run_id) == 36  # UUID format

            tracer.close()

    def test_create_tracer_uses_constant_api_url(self):
        """Test create_tracer uses constant SENTIENCE_API_URL."""
        from sentience.tracer_factory import SENTIENCE_API_URL

        with patch("sentience.tracer_factory.requests.post") as mock_post:
            with patch("sentience.cloud_tracing.requests.put") as mock_put:
                # Mock API response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"upload_url": "https://storage.com/upload"}
                mock_post.return_value = mock_response
                mock_put.return_value = Mock(status_code=200)

                tracer = create_tracer(api_key="sk_test123", run_id="test-run", upload_trace=True)

                # Verify correct API URL was used (constant)
                assert mock_post.called
                call_args = mock_post.call_args
                assert call_args[0][0] == f"{SENTIENCE_API_URL}/v1/traces/init"
                assert SENTIENCE_API_URL == "https://api.sentienceapi.com"

                tracer.close()

    def test_create_tracer_custom_api_url(self):
        """Test create_tracer accepts custom api_url parameter."""
        custom_api_url = "https://custom.api.example.com"

        with patch("sentience.tracer_factory.requests.post") as mock_post:
            with patch("sentience.cloud_tracing.requests.put") as mock_put:
                # Mock API response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"upload_url": "https://storage.com/upload"}
                mock_post.return_value = mock_response
                mock_put.return_value = Mock(status_code=200)

                tracer = create_tracer(
                    api_key="sk_test123",
                    run_id="test-run",
                    api_url=custom_api_url,
                    upload_trace=True,
                )

                # Verify custom API URL was used
                assert mock_post.called
                call_args = mock_post.call_args
                assert call_args[0][0] == f"{custom_api_url}/v1/traces/init"

                tracer.close()

    def test_create_tracer_missing_upload_url_in_response(self, capsys):
        """Test create_tracer handles missing upload_url gracefully."""
        with patch("sentience.tracer_factory.requests.post") as mock_post:
            # Mock API response without upload_url
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message": "Success"}  # Missing upload_url
            mock_post.return_value = mock_response

            with tempfile.TemporaryDirectory():
                tracer = create_tracer(api_key="sk_test123", run_id="test-run", upload_trace=True)

                # Verify warning message
                captured = capsys.readouterr()
                assert "⚠️  [Sentience] Cloud init response missing upload_url" in captured.out

                # Verify fallback to local
                assert isinstance(tracer.sink, JsonlTraceSink)

                tracer.close()

    def test_create_tracer_orphaned_trace_recovery(self, capsys):
        """Test create_tracer recovers and uploads orphaned traces from previous crashes."""
        import gzip
        from pathlib import Path

        # Create orphaned trace file
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        cache_dir.mkdir(parents=True, exist_ok=True)
        orphaned_run_id = "orphaned-run-123"
        orphaned_path = cache_dir / f"{orphaned_run_id}.jsonl"

        # Write test trace data
        with open(orphaned_path, "w") as f:
            f.write('{"v": 1, "type": "run_start", "seq": 1}\n')

        try:
            with patch("sentience.tracer_factory.requests.post") as mock_post:
                with patch("sentience.tracer_factory.requests.put") as mock_put:
                    # Mock API response for orphaned trace recovery
                    mock_recovery_response = Mock()
                    mock_recovery_response.status_code = 200
                    mock_recovery_response.json.return_value = {
                        "upload_url": "https://storage.com/orphaned-upload"
                    }

                    # Mock API response for new tracer creation
                    mock_new_response = Mock()
                    mock_new_response.status_code = 200
                    mock_new_response.json.return_value = {
                        "upload_url": "https://storage.com/new-upload"
                    }

                    # First call for orphaned recovery, second for new tracer
                    mock_post.side_effect = [mock_recovery_response, mock_new_response]
                    mock_put.return_value = Mock(status_code=200)

                    # Create tracer - should trigger orphaned trace recovery
                    tracer = create_tracer(
                        api_key="sk_test123", run_id="new-run-456", upload_trace=True
                    )

                    # Verify recovery messages
                    captured = capsys.readouterr()
                    assert "Found" in captured.out and "un-uploaded trace" in captured.out
                    assert "Uploaded orphaned trace" in captured.out or "Failed" in captured.out

                    # Verify orphaned file was processed (either uploaded and deleted, or failed)
                    # If successful, file should be deleted
                    # If failed, file should still exist
                    # We check that recovery was attempted
                    assert mock_post.call_count >= 1, "Orphaned trace recovery should be attempted"

                    # Verify new tracer was created
                    assert tracer.run_id == "new-run-456"

                    tracer.close()

        finally:
            # Cleanup orphaned file if it still exists
            if orphaned_path.exists():
                os.remove(orphaned_path)


class TestRegressionTests:
    """Regression tests to ensure cloud tracing doesn't break existing functionality."""

    def test_local_tracing_still_works(self):
        """Test existing JsonlTraceSink functionality unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"

            with JsonlTraceSink(trace_path) as sink:
                tracer = Tracer(run_id="test-run", sink=sink)
                tracer.emit_run_start("TestAgent", "gpt-4")
                tracer.emit_run_end(1)

            # Verify trace file created
            assert trace_path.exists()

            lines = trace_path.read_text().strip().split("\n")
            assert len(lines) == 2

            event1 = json.loads(lines[0])
            assert event1["type"] == "run_start"

    def test_tracer_api_unchanged(self):
        """Test Tracer API hasn't changed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            sink = JsonlTraceSink(trace_path)

            # All existing methods should still work
            tracer = Tracer(run_id="test-run", sink=sink)

            tracer.emit("custom_event", {"data": "value"})
            tracer.emit_run_start("TestAgent")
            tracer.emit_step_start("step-1", 1, "Test goal")
            tracer.emit_error("step-1", "Test error")
            tracer.emit_run_end(1)

            tracer.close()

            # Verify all events written
            lines = trace_path.read_text().strip().split("\n")
            assert len(lines) == 5

    def test_cloud_trace_sink_index_upload_success(self):
        """Test CloudTraceSink uploads index file after trace upload."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/traces/test.jsonl.gz"
        run_id = "test-index-upload"

        with (
            patch("sentience.cloud_tracing.requests.put") as mock_put,
            patch("sentience.cloud_tracing.requests.post") as mock_post,
        ):
            # Mock successful trace upload
            trace_response = Mock()
            trace_response.status_code = 200

            # Mock successful index upload URL request
            index_url_response = Mock()
            index_url_response.status_code = 200
            index_url_response.json.return_value = {
                "upload_url": "https://sentience.nyc3.digitaloceanspaces.com/traces/test.index.json.gz"
            }

            # Mock successful /v1/traces/complete response
            complete_response = Mock()
            complete_response.status_code = 200

            # Mock successful index upload
            index_upload_response = Mock()
            index_upload_response.status_code = 200

            mock_put.side_effect = [trace_response, index_upload_response]
            # POST is called twice: once for index_upload, once for complete
            mock_post.side_effect = [index_url_response, complete_response]

            # Create sink and emit events
            sink = CloudTraceSink(upload_url, run_id=run_id, api_key="sk_test_123")
            sink.emit({"v": 1, "type": "run_start", "seq": 1, "data": {"agent": "TestAgent"}})
            sink.emit({"v": 1, "type": "step_start", "seq": 2, "data": {"step": 1}})
            sink.emit(
                {"v": 1, "type": "snapshot", "seq": 3, "data": {"url": "https://example.com"}}
            )
            sink.emit({"v": 1, "type": "run_end", "seq": 4, "data": {"steps": 1}})

            # Close triggers upload
            sink.close()

            # Verify trace upload
            assert mock_put.call_count == 2  # Once for trace, once for index

            # Verify index upload URL request (first POST call)
            assert mock_post.called
            assert mock_post.call_count == 2  # index_upload + complete

            # Check first POST call (index_upload)
            first_post_call = mock_post.call_args_list[0]
            assert "/v1/traces/index_upload" in first_post_call[0][0]
            assert first_post_call[1]["json"] == {"run_id": run_id}

            # Verify index file upload
            index_call = mock_put.call_args_list[1]
            assert "index.json.gz" in index_call[0][0]
            assert index_call[1]["headers"]["Content-Type"] == "application/json"
            assert index_call[1]["headers"]["Content-Encoding"] == "gzip"

            # Cleanup
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            index_path = cache_dir / f"{run_id}.index.json"
            if index_path.exists():
                os.remove(index_path)

    def test_cloud_trace_sink_index_upload_no_api_key(self):
        """Test CloudTraceSink skips index upload when no API key provided."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/traces/test.jsonl.gz"
        run_id = "test-no-api-key"

        with (
            patch("sentience.cloud_tracing.requests.put") as mock_put,
            patch("sentience.cloud_tracing.requests.post") as mock_post,
        ):
            # Mock successful trace upload
            mock_put.return_value = Mock(status_code=200)

            # Create sink WITHOUT api_key
            sink = CloudTraceSink(upload_url, run_id=run_id)
            sink.emit({"v": 1, "type": "run_start", "seq": 1})

            sink.close()

            # Verify trace upload happened
            assert mock_put.called

            # Verify index upload was NOT attempted (no API key)
            assert not mock_post.called

            # Cleanup
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            index_path = cache_dir / f"{run_id}.index.json"
            if trace_path.exists():
                os.remove(trace_path)
            if index_path.exists():
                os.remove(index_path)

    def test_cloud_trace_sink_index_upload_failure_non_fatal(self, capsys):
        """Test CloudTraceSink continues gracefully if index upload fails."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/traces/test.jsonl.gz"
        run_id = "test-index-fail"

        with (
            patch("sentience.cloud_tracing.requests.put") as mock_put,
            patch("sentience.cloud_tracing.requests.post") as mock_post,
        ):
            # Mock successful trace upload
            trace_response = Mock()
            trace_response.status_code = 200

            # Mock failed index upload URL request
            index_url_response = Mock()
            index_url_response.status_code = 500

            mock_put.return_value = trace_response
            mock_post.return_value = index_url_response

            # Create sink
            sink = CloudTraceSink(upload_url, run_id=run_id, api_key="sk_test_123")
            sink.emit({"v": 1, "type": "run_start", "seq": 1})

            # Close should succeed even if index upload fails
            sink.close()

            # Verify trace upload succeeded
            assert mock_put.called

            # Verify warning was printed
            captured = capsys.readouterr()
            # Index upload failure is non-fatal, so main upload should succeed
            assert "✅" in captured.out  # Trace upload success

            # Cleanup
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            index_path = cache_dir / f"{run_id}.index.json"
            if trace_path.exists():
                os.remove(trace_path)
            if index_path.exists():
                os.remove(index_path)

    def test_cloud_trace_sink_index_file_missing(self, capsys):
        """Test CloudTraceSink handles missing index file gracefully."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/traces/test.jsonl.gz"
        run_id = "test-missing-index"

        with (
            patch("sentience.cloud_tracing.requests.put") as mock_put,
            patch("sentience.cloud_tracing.requests.post") as mock_post,
            patch("sentience.trace_indexing.write_trace_index") as mock_write_index,
        ):
            # Mock index generation to fail (simulating missing index)
            mock_write_index.side_effect = Exception("Index generation failed")

            # Mock successful trace upload
            mock_put.return_value = Mock(status_code=200)

            # Mock /v1/traces/complete response (this will still be called)
            complete_response = Mock()
            complete_response.status_code = 200
            mock_post.return_value = complete_response

            # Create sink
            sink = CloudTraceSink(upload_url, run_id=run_id, api_key="sk_test_123")
            sink.emit({"v": 1, "type": "run_start", "seq": 1})

            # Close should succeed even if index generation fails
            sink.close()

            # Verify trace upload succeeded
            assert mock_put.called

            # POST is called once for /v1/traces/complete, but NOT for /v1/traces/index_upload
            # (because index file is missing)
            assert mock_post.call_count == 1
            # Verify it was the complete call, not index_upload
            assert "/v1/traces/complete" in mock_post.call_args[0][0]

            # Verify warning was printed
            captured = capsys.readouterr()
            assert "⚠️" in captured.out
            assert "Failed to generate trace index" in captured.out

            # Cleanup
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            if trace_path.exists():
                os.remove(trace_path)

    def test_cloud_trace_sink_completion_includes_all_stats(self):
        """Test that _complete_trace() includes all required stats fields."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-complete-stats"
        api_key = "sk_test_123"

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        # Emit events with timestamps
        from datetime import datetime

        start_time = datetime.utcnow()
        sink.emit(
            {
                "v": 1,
                "type": "run_start",
                "ts": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "run_id": run_id,
                "seq": 1,
                "data": {"agent": "TestAgent"},
            }
        )

        sink.emit(
            {
                "v": 1,
                "type": "step_start",
                "ts": start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "run_id": run_id,
                "seq": 2,
                "step_id": "step-1",
                "data": {"step_id": "step-1", "step_index": 1, "goal": "Test", "attempt": 0},
            }
        )

        end_time = datetime.utcnow()
        sink.emit(
            {
                "v": 1,
                "type": "run_end",
                "ts": end_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "run_id": run_id,
                "seq": 3,
                "data": {"steps": 1, "status": "success"},
            }
        )

        with (
            patch("sentience.cloud_tracing.requests.put") as mock_put,
            patch("sentience.cloud_tracing.requests.post") as mock_post,
        ):
            # Mock successful trace upload
            mock_put.return_value = Mock(status_code=200)

            # Mock index upload (optional)
            mock_index_response = Mock()
            mock_index_response.status_code = 200
            mock_index_response.json.return_value = {"upload_url": "https://example.com/index"}

            # Mock completion response
            mock_complete_response = Mock()
            mock_complete_response.status_code = 200

            def post_side_effect(*args, **kwargs):
                url = args[0] if args else kwargs.get("url", "")
                if "index_upload" in url:
                    return mock_index_response
                return mock_complete_response

            mock_post.side_effect = post_side_effect

            sink.close()

            # Verify completion was called
            complete_calls = [call for call in mock_post.call_args_list if "complete" in call[0][0]]
            assert len(complete_calls) > 0, "Completion request should have been called"

            complete_call = complete_calls[0]
            complete_data = complete_call[1].get("json", {})
            stats = complete_data.get("stats", {})

            # Verify all required fields are present
            assert "trace_file_size_bytes" in stats
            assert "screenshot_total_size_bytes" in stats
            assert "screenshot_count" in stats
            assert "index_file_size_bytes" in stats
            assert "total_steps" in stats
            assert stats["total_steps"] == 1
            assert "total_events" in stats
            assert stats["total_events"] == 3
            assert "duration_ms" in stats
            assert stats["duration_ms"] is not None
            assert "final_status" in stats
            assert stats["final_status"] == "success"
            assert "started_at" in stats
            assert stats["started_at"] is not None
            assert "ended_at" in stats
            assert stats["ended_at"] is not None

        # Cleanup
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        if trace_path.exists():
            os.remove(trace_path)
