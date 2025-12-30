"""Tests for sentience.cloud_tracing module"""

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
        sink.close()

        with pytest.raises(RuntimeError, match="CloudTraceSink is closed"):
            sink.emit({"v": 1, "type": "test", "seq": 1})

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

            # Should not raise, just print warning
            sink.close()

            captured = capsys.readouterr()
            assert "❌" in captured.out
            assert "Error uploading trace" in captured.out

            # Verify file was preserved
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            assert trace_path.exists(), "Trace file should be preserved on network error"

            # Cleanup
            if trace_path.exists():
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
                assert isinstance(tracer.sink, CloudTraceSink)
                assert tracer.sink.run_id == "test-run"  # Verify run_id is passed

                # Cleanup
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

        with patch("sentience.cloud_tracing.requests.put") as mock_put, \
             patch("sentience.cloud_tracing.requests.post") as mock_post:
            # Mock successful trace upload
            trace_response = Mock()
            trace_response.status_code = 200

            # Mock successful index upload URL request
            index_url_response = Mock()
            index_url_response.status_code = 200
            index_url_response.json.return_value = {
                "upload_url": "https://sentience.nyc3.digitaloceanspaces.com/traces/test.index.json.gz"
            }

            # Mock successful index upload
            index_upload_response = Mock()
            index_upload_response.status_code = 200

            mock_put.side_effect = [trace_response, index_upload_response]
            mock_post.return_value = index_url_response

            # Create sink and emit events
            sink = CloudTraceSink(upload_url, run_id=run_id, api_key="sk_test_123")
            sink.emit({"v": 1, "type": "run_start", "seq": 1, "data": {"agent": "TestAgent"}})
            sink.emit({"v": 1, "type": "step_start", "seq": 2, "data": {"step": 1}})
            sink.emit({"v": 1, "type": "snapshot", "seq": 3, "data": {"url": "https://example.com"}})
            sink.emit({"v": 1, "type": "run_end", "seq": 4, "data": {"steps": 1}})

            # Close triggers upload
            sink.close()

            # Verify trace upload
            assert mock_put.call_count == 2  # Once for trace, once for index

            # Verify index upload URL request
            assert mock_post.called
            assert "/v1/traces/index_upload" in mock_post.call_args[0][0]
            assert mock_post.call_args[1]["json"] == {"run_id": run_id}

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

        with patch("sentience.cloud_tracing.requests.put") as mock_put, \
             patch("sentience.cloud_tracing.requests.post") as mock_post:
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

        with patch("sentience.cloud_tracing.requests.put") as mock_put, \
             patch("sentience.cloud_tracing.requests.post") as mock_post:
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

        with patch("sentience.cloud_tracing.requests.put") as mock_put, \
             patch("sentience.cloud_tracing.requests.post") as mock_post, \
             patch("sentience.cloud_tracing.write_trace_index") as mock_write_index:
            # Mock index generation to fail (simulating missing index)
            mock_write_index.side_effect = Exception("Index generation failed")

            # Mock successful trace upload
            mock_put.return_value = Mock(status_code=200)

            # Create sink
            sink = CloudTraceSink(upload_url, run_id=run_id, api_key="sk_test_123")
            sink.emit({"v": 1, "type": "run_start", "seq": 1})

            # Close should succeed even if index generation fails
            sink.close()

            # Verify trace upload succeeded
            assert mock_put.called

            # Verify index upload was not attempted (index file missing)
            assert not mock_post.called

            # Verify warning was printed
            captured = capsys.readouterr()
            assert "⚠️" in captured.out
            assert "Failed to generate trace index" in captured.out

            # Cleanup
            cache_dir = Path.home() / ".sentience" / "traces" / "pending"
            trace_path = cache_dir / f"{run_id}.jsonl"
            if trace_path.exists():
                os.remove(trace_path)
