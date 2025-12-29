"""
Tests for file size tracking and /v1/traces/complete functionality.

Tests the Phase 5 SDK changes for enforcing storage quota.
"""

import gzip
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from sentience.cloud_tracing import CloudTraceSink, SentienceLogger
from sentience.tracer_factory import create_tracer
from sentience.tracing import Tracer


class TestFileSizeTracking:
    """Test file size tracking in CloudTraceSink."""

    def test_cloud_sink_tracks_trace_file_size(self, tmp_path):
        """Test that CloudTraceSink measures compressed trace file size."""
        # Create mock logger
        mock_logger = Mock(spec=SentienceLogger)

        # Create mock upload URL
        upload_url = "https://example.com/upload"

        # Create CloudTraceSink with logger
        sink = CloudTraceSink(
            upload_url=upload_url,
            run_id="test-run",
            api_key="sk_test_key",
            api_url="https://api.example.com",
            logger=mock_logger,
        )

        # Verify logger is set
        assert sink.logger == mock_logger

        # Verify file size tracking fields exist
        assert hasattr(sink, "trace_file_size_bytes")
        assert hasattr(sink, "screenshot_total_size_bytes")
        assert sink.trace_file_size_bytes == 0
        assert sink.screenshot_total_size_bytes == 0

    def test_cloud_sink_without_logger(self):
        """Test that CloudTraceSink works without a logger (backward compatibility)."""
        upload_url = "https://example.com/upload"

        # Create CloudTraceSink without logger (should not fail)
        sink = CloudTraceSink(
            upload_url=upload_url,
            run_id="test-run",
        )

        assert sink.logger is None
        assert sink.trace_file_size_bytes == 0
        assert sink.screenshot_total_size_bytes == 0

    @patch("sentience.cloud_tracing.requests")
    def test_cloud_sink_logs_file_sizes(self, mock_requests):
        """Test that CloudTraceSink logs file sizes when logger is provided."""
        # Create mock logger
        mock_logger = Mock(spec=SentienceLogger)

        # Mock successful upload
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.put.return_value = mock_response
        mock_requests.post.return_value = mock_response

        upload_url = "https://example.com/upload"

        # Create CloudTraceSink with logger
        sink = CloudTraceSink(
            upload_url=upload_url,
            run_id="test-run-size",
            api_key="sk_test_key",
            logger=mock_logger,
        )

        # Emit some events
        sink.emit({"type": "test", "data": "test"})

        # Close to trigger upload
        sink.close()

        # Verify logger.info was called with file size information
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Trace file size:" in call for call in info_calls)
        assert any("Screenshot total:" in call for call in info_calls)

    @patch("sentience.cloud_tracing.requests")
    def test_complete_trace_called_after_upload(self, mock_requests):
        """Test that /v1/traces/complete is called after successful upload."""
        # Mock successful upload and complete
        mock_put_response = Mock()
        mock_put_response.status_code = 200

        mock_post_response = Mock()
        mock_post_response.status_code = 200

        mock_requests.put.return_value = mock_put_response
        mock_requests.post.return_value = mock_post_response

        upload_url = "https://example.com/upload"
        api_url = "https://api.example.com"

        # Create CloudTraceSink with API key
        sink = CloudTraceSink(
            upload_url=upload_url,
            run_id="test-complete",
            api_key="sk_test_key",
            api_url=api_url,
        )

        # Emit event and close
        sink.emit({"type": "test"})
        sink.close()

        # Verify /v1/traces/complete was called
        post_calls = mock_requests.post.call_args_list
        assert len(post_calls) > 0

        # Find the complete trace call
        complete_call = None
        for call in post_calls:
            args, kwargs = call
            if "/v1/traces/complete" in args[0]:
                complete_call = call
                break

        assert complete_call is not None, "Expected /v1/traces/complete to be called"

        # Verify the payload
        args, kwargs = complete_call
        payload = kwargs.get("json") or json.loads(kwargs.get("data", "{}"))
        assert "run_id" in payload
        assert payload["run_id"] == "test-complete"
        assert "stats" in payload
        assert "trace_file_size_bytes" in payload["stats"]
        assert "screenshot_total_size_bytes" in payload["stats"]

    @patch("sentience.cloud_tracing.requests")
    def test_complete_trace_not_called_without_api_key(self, mock_requests):
        """Test that /v1/traces/complete is not called without API key."""
        # Mock successful upload
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.put.return_value = mock_response

        upload_url = "https://example.com/upload"

        # Create CloudTraceSink WITHOUT API key
        sink = CloudTraceSink(
            upload_url=upload_url,
            run_id="test-no-key",
        )

        # Emit event and close
        sink.emit({"type": "test"})
        sink.close()

        # Verify POST was NOT called
        assert mock_requests.post.call_count == 0

    @patch("sentience.tracer_factory.requests")
    def test_create_tracer_passes_logger_to_cloud_sink(self, mock_requests):
        """Test that create_tracer passes logger to CloudTraceSink."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"upload_url": "https://example.com/upload"}
        mock_requests.post.return_value = mock_response

        # Create mock logger
        mock_logger = Mock(spec=SentienceLogger)

        # Create tracer with logger
        with patch("sentience.tracer_factory._recover_orphaned_traces"):
            tracer = create_tracer(
                api_key="sk_test_key",
                run_id="test-logger",
                logger=mock_logger,
            )

        # Verify tracer was created
        assert isinstance(tracer, Tracer)

        # Verify sink has logger
        assert hasattr(tracer.sink, "logger")
        assert tracer.sink.logger == mock_logger


class TestBackwardCompatibility:
    """Test that existing code continues to work."""

    @patch("sentience.tracer_factory.requests")
    def test_create_tracer_without_logger_still_works(self, mock_requests):
        """Test that create_tracer works without logger parameter (backward compat)."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"upload_url": "https://example.com/upload"}
        mock_requests.post.return_value = mock_response

        # Create tracer WITHOUT logger (old API)
        with patch("sentience.tracer_factory._recover_orphaned_traces"):
            tracer = create_tracer(
                api_key="sk_test_key",
                run_id="test-compat",
            )

        # Should still work
        assert isinstance(tracer, Tracer)

    def test_cloud_sink_backward_compatible_signature(self):
        """Test that CloudTraceSink can be created with old 2-parameter signature."""
        # Old signature: CloudTraceSink(upload_url, run_id)
        sink = CloudTraceSink(
            upload_url="https://example.com/upload",
            run_id="test-old-api",
        )

        # Should work fine
        assert sink.upload_url == "https://example.com/upload"
        assert sink.run_id == "test-old-api"
        assert sink.logger is None  # No logger
        assert sink.api_key is None  # No API key
