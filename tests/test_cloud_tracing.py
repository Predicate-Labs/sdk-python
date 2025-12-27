"""Tests for sentience.cloud_tracing module"""

import gzip
import json
import tempfile
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

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Success"
            mock_put.return_value = mock_response

            # Create sink and emit events
            sink = CloudTraceSink(upload_url)
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

    def test_cloud_trace_sink_upload_failure_preserves_trace(self, capsys):
        """Test CloudTraceSink preserves trace locally on upload failure."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            # Mock failed response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_put.return_value = mock_response

            # Create sink and emit events
            sink = CloudTraceSink(upload_url)
            sink.emit({"v": 1, "type": "run_start", "seq": 1})

            # Close triggers upload (which will fail)
            sink.close()

            # Verify error message printed
            captured = capsys.readouterr()
            assert "❌" in captured.out
            assert "Upload failed: HTTP 500" in captured.out
            assert "Local trace preserved" in captured.out

    def test_cloud_trace_sink_emit_after_close_raises(self):
        """Test CloudTraceSink raises error when emitting after close."""
        upload_url = "https://test.com/upload"
        sink = CloudTraceSink(upload_url)
        sink.close()

        with pytest.raises(RuntimeError, match="CloudTraceSink is closed"):
            sink.emit({"v": 1, "type": "test", "seq": 1})

    def test_cloud_trace_sink_context_manager(self):
        """Test CloudTraceSink works as context manager."""
        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)

            upload_url = "https://test.com/upload"
            with CloudTraceSink(upload_url) as sink:
                sink.emit({"v": 1, "type": "test", "seq": 1})

            # Verify upload was called
            assert mock_put.called

    def test_cloud_trace_sink_network_error_graceful_degradation(self, capsys):
        """Test CloudTraceSink handles network errors gracefully."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"

        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            # Simulate network error
            mock_put.side_effect = Exception("Network error")

            sink = CloudTraceSink(upload_url)
            sink.emit({"v": 1, "type": "test", "seq": 1})

            # Should not raise, just print warning
            sink.close()

            captured = capsys.readouterr()
            assert "❌" in captured.out
            assert "Error uploading trace" in captured.out

    def test_cloud_trace_sink_multiple_close_safe(self):
        """Test CloudTraceSink.close() is idempotent."""
        with patch("sentience.cloud_tracing.requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)

            upload_url = "https://test.com/upload"
            sink = CloudTraceSink(upload_url)
            sink.emit({"v": 1, "type": "test", "seq": 1})

            # Close multiple times
            sink.close()
            sink.close()
            sink.close()

            # Upload should only be called once
            assert mock_put.call_count == 1


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

                tracer = create_tracer(api_key="sk_pro_test123", run_id="test-run")

                # Verify Pro tier message
                captured = capsys.readouterr()
                assert "☁️  [Sentience] Cloud tracing enabled (Pro tier)" in captured.out

                # Verify tracer works
                assert tracer.run_id == "test-run"
                assert isinstance(tracer.sink, CloudTraceSink)

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
                tracer = create_tracer(api_key="sk_free_test123", run_id="test-run")

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
                tracer = create_tracer(api_key="sk_test123", run_id="test-run")

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
                tracer = create_tracer(api_key="sk_test123", run_id="test-run")

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

    def test_create_tracer_custom_api_url(self):
        """Test create_tracer with custom API URL."""
        custom_url = "https://custom.api.com"

        with patch("sentience.tracer_factory.requests.post") as mock_post:
            with patch("sentience.cloud_tracing.requests.put") as mock_put:
                # Mock API response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"upload_url": "https://storage.com/upload"}
                mock_post.return_value = mock_response
                mock_put.return_value = Mock(status_code=200)

                tracer = create_tracer(api_key="sk_test123", run_id="test-run", api_url=custom_url)

                # Verify correct API URL was used
                assert mock_post.called
                call_args = mock_post.call_args
                assert call_args[0][0] == f"{custom_url}/v1/traces/init"

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
                tracer = create_tracer(api_key="sk_test123", run_id="test-run")

                # Verify warning message
                captured = capsys.readouterr()
                assert "⚠️  [Sentience] Cloud init response missing upload_url" in captured.out

                # Verify fallback to local
                assert isinstance(tracer.sink, JsonlTraceSink)

                tracer.close()


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
