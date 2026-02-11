"""Tests for screenshot extraction and upload in CloudTraceSink"""

import base64
import gzip
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from predicate.cloud_tracing import CloudTraceSink


class TestScreenshotExtraction:
    """Test screenshot extraction functionality in CloudTraceSink."""

    def test_extract_screenshots_from_trace(self):
        """Test that _extract_screenshots_from_trace extracts screenshots from events."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-extraction-1"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Emit a snapshot event with screenshot
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

        # Finalize trace file synchronously (closes file handle properly)
        # Using _finalize_trace_file_for_upload instead of close(blocking=False)
        # to avoid Windows file locking issues in tests
        sink._finalize_trace_file_for_upload()

        # Extract screenshots
        screenshots = sink._extract_screenshots_from_trace()

        assert len(screenshots) == 1
        assert 1 in screenshots
        assert screenshots[1]["base64"] == test_image_base64
        assert screenshots[1]["format"] == "png"
        assert screenshots[1]["step_id"] == "step-1"

        # Cleanup - file handle is already closed
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        if trace_path.exists():
            trace_path.unlink()

    def test_extract_screenshots_handles_multiple(self):
        """Test that _extract_screenshots_from_trace handles multiple screenshots."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-extraction-2"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Emit multiple snapshot events with screenshots
        for i in range(1, 4):
            sink.emit(
                {
                    "v": 1,
                    "type": "snapshot",
                    "ts": "2026-01-01T00:00:00.000Z",
                    "run_id": run_id,
                    "seq": i,
                    "step_id": f"step-{i}",
                    "data": {
                        "url": "https://example.com",
                        "element_count": 10,
                        "screenshot_base64": test_image_base64,
                        "screenshot_format": "png",
                    },
                }
            )

        # Finalize trace file synchronously (closes file handle properly)
        # Using _finalize_trace_file_for_upload instead of close(blocking=False)
        # to avoid Windows file locking issues in tests
        sink._finalize_trace_file_for_upload()

        screenshots = sink._extract_screenshots_from_trace()
        assert len(screenshots) == 3

        # Cleanup - file handle is already closed
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        if trace_path.exists():
            trace_path.unlink()

    def test_extract_screenshots_skips_events_without_screenshots(self):
        """Test that _extract_screenshots_from_trace skips events without screenshots."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-extraction-3"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Emit snapshot without screenshot
        sink.emit(
            {
                "v": 1,
                "type": "snapshot",
                "ts": "2026-01-01T00:00:00.000Z",
                "run_id": run_id,
                "seq": 1,
                "data": {
                    "url": "https://example.com",
                    "element_count": 10,
                    # No screenshot_base64
                },
            }
        )

        # Finalize trace file synchronously (closes file handle properly)
        # Using _finalize_trace_file_for_upload instead of close(blocking=False)
        # to avoid Windows file locking issues in tests
        sink._finalize_trace_file_for_upload()

        screenshots = sink._extract_screenshots_from_trace()
        assert len(screenshots) == 0

        # Cleanup - file handle is already closed
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        if trace_path.exists():
            trace_path.unlink()


class TestCleanedTrace:
    """Test cleaned trace creation functionality."""

    def test_create_cleaned_trace_removes_screenshot_fields(self):
        """Test that _create_cleaned_trace removes screenshot_base64 from events."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-cleaned-trace-1"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Emit snapshot event with screenshot
        sink.emit(
            {
                "v": 1,
                "type": "snapshot",
                "ts": "2026-01-01T00:00:00.000Z",
                "run_id": run_id,
                "seq": 1,
                "data": {
                    "url": "https://example.com",
                    "element_count": 10,
                    "screenshot_base64": test_image_base64,
                    "screenshot_format": "png",
                },
            }
        )

        # Finalize trace file synchronously to avoid Windows file locking issues
        sink._finalize_trace_file_for_upload()

        # Create cleaned trace
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        cleaned_trace_path = cache_dir / f"{run_id}.cleaned.jsonl"
        sink._create_cleaned_trace(cleaned_trace_path)

        # Read cleaned trace
        with open(cleaned_trace_path) as f:
            cleaned_event = json.loads(f.readline())

        # Verify screenshot fields are removed
        assert "screenshot_base64" not in cleaned_event["data"]
        assert "screenshot_format" not in cleaned_event["data"]
        assert cleaned_event["data"]["url"] == "https://example.com"
        assert cleaned_event["data"]["element_count"] == 10

        # Cleanup
        trace_path = cache_dir / f"{run_id}.jsonl"
        if trace_path.exists():
            trace_path.unlink()
        if cleaned_trace_path.exists():
            cleaned_trace_path.unlink()

    def test_create_cleaned_trace_preserves_other_events(self):
        """Test that _create_cleaned_trace preserves non-snapshot events unchanged."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-cleaned-trace-2"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Emit non-snapshot event
        sink.emit(
            {
                "v": 1,
                "type": "action",
                "ts": "2026-01-01T00:00:00.000Z",
                "run_id": run_id,
                "seq": 1,
                "data": {
                    "action": "click",
                    "element_id": 123,
                },
            }
        )

        # Finalize trace file synchronously to avoid Windows file locking issues
        sink._finalize_trace_file_for_upload()

        # Create cleaned trace
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        cleaned_trace_path = cache_dir / f"{run_id}.cleaned.jsonl"
        sink._create_cleaned_trace(cleaned_trace_path)

        # Read cleaned trace
        with open(cleaned_trace_path) as f:
            cleaned_event = json.loads(f.readline())

        # Verify action event is unchanged
        assert cleaned_event["type"] == "action"
        assert cleaned_event["data"]["action"] == "click"
        assert cleaned_event["data"]["element_id"] == 123

        # Cleanup
        trace_path = cache_dir / f"{run_id}.jsonl"
        if trace_path.exists():
            trace_path.unlink()
        if cleaned_trace_path.exists():
            cleaned_trace_path.unlink()


class TestScreenshotUpload:
    """Test screenshot upload functionality in CloudTraceSink."""

    def test_request_screenshot_urls_success(self):
        """Test that _request_screenshot_urls requests URLs from gateway."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-upload-1"
        api_key = "sk_test_123"

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        # Mock gateway response
        mock_urls = {
            "1": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0001.png?signature=...",
            "2": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0002.png?signature=...",
        }

        with patch("predicate.cloud_tracing.requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"upload_urls": mock_urls}
            mock_post.return_value = mock_response

            # Request URLs
            result = sink._request_screenshot_urls([1, 2])

            # Verify request was made
            assert mock_post.called
            call_args = mock_post.call_args
            assert "v1/screenshots/init" in call_args[0][0]
            assert call_args[1]["headers"]["Authorization"] == f"Bearer {api_key}"
            assert call_args[1]["json"]["run_id"] == run_id
            assert call_args[1]["json"]["sequences"] == [1, 2]

            # Verify result (keys converted to int)
            assert result == {1: mock_urls["1"], 2: mock_urls["2"]}

        sink.close(blocking=False)

    def test_request_screenshot_urls_handles_failure(self):
        """Test that _request_screenshot_urls handles gateway failure."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-upload-2"
        api_key = "sk_test_123"

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        with patch("predicate.cloud_tracing.requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response

            # Request URLs (should return empty dict on failure)
            result = sink._request_screenshot_urls([1, 2])
            assert result == {}

        sink.close(blocking=False)

    def test_upload_screenshots_uploads_in_parallel(self):
        """Test that _upload_screenshots uploads screenshots in parallel."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-upload-3"
        api_key = "sk_test_123"

        # Create test screenshots data
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        screenshots = {
            1: {"base64": test_image_base64, "format": "png", "step_id": "step-1"},
            2: {"base64": test_image_base64, "format": "png", "step_id": "step-2"},
        }

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        # Mock gateway and upload responses
        mock_upload_urls = {
            "1": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0001.png?signature=...",
            "2": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0002.png?signature=...",
        }

        with (
            patch("predicate.cloud_tracing.requests.post") as mock_post,
            patch("predicate.cloud_tracing.requests.put") as mock_put,
        ):
            # Mock gateway response
            mock_gateway_response = Mock()
            mock_gateway_response.status_code = 200
            mock_gateway_response.json.return_value = {"upload_urls": mock_upload_urls}
            mock_post.return_value = mock_gateway_response

            # Mock upload responses
            mock_upload_response = Mock()
            mock_upload_response.status_code = 200
            mock_put.return_value = mock_upload_response

            # Upload screenshots
            sink._upload_screenshots(screenshots)

            # Verify gateway was called
            assert mock_post.called

            # Verify uploads were called (2 screenshots)
            # Filter PUT calls to only screenshot uploads (exclude trace file uploads)
            put_calls = mock_put.call_args_list
            screenshot_uploads = [
                call for call in put_calls if "screenshots" in str(call[0][0] if call[0] else "")
            ]
            assert len(screenshot_uploads) == 2

            # Verify upload URLs and content
            upload_urls = [call[0][0] for call in screenshot_uploads]
            assert mock_upload_urls["1"] in upload_urls
            assert mock_upload_urls["2"] in upload_urls

        sink.close(blocking=False)

    def test_upload_screenshots_skips_when_no_screenshots(self, capsys):
        """Test that _upload_screenshots skips when no screenshots provided."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-upload-4"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Call upload with no screenshots (should do nothing)
        sink._upload_screenshots({})

        # Verify no errors
        captured = capsys.readouterr()
        assert "Uploading" not in captured.out

        sink.close(blocking=False)

    def test_complete_trace_includes_screenshot_count(self):
        """Test that _complete_trace includes screenshot_count in stats."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-complete-1"
        api_key = "sk_test_123"

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)
        # Set screenshot count (normally set during extraction)
        sink.screenshot_count = 2

        with patch("predicate.cloud_tracing.requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            # Call complete
            sink._complete_trace()

            # Verify request included screenshot_count
            assert mock_post.called
            call_args = mock_post.call_args
            stats = call_args[1]["json"]["stats"]
            assert "screenshot_count" in stats
            assert stats["screenshot_count"] == 2

        sink.close(blocking=False)

    def test_upload_removes_screenshot_base64_from_trace(self):
        """Test that uploaded trace data does not contain screenshot_base64."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-upload-clean-1"
        api_key = "sk_test_123"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        # Emit snapshot event with screenshot
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

        # Finalize trace file synchronously to avoid Windows file locking issues
        sink._finalize_trace_file_for_upload()

        # Mock gateway and upload responses
        mock_upload_urls = {
            "1": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0001.png?signature=...",
        }

        with (
            patch("predicate.cloud_tracing.requests.post") as mock_post,
            patch("predicate.cloud_tracing.requests.put") as mock_put,
        ):
            # Mock gateway response for screenshot URLs
            mock_gateway_response = Mock()
            mock_gateway_response.status_code = 200
            mock_gateway_response.json.return_value = {"upload_urls": mock_upload_urls}
            mock_post.return_value = mock_gateway_response

            # Mock screenshot upload response
            mock_screenshot_upload = Mock()
            mock_screenshot_upload.status_code = 200
            mock_put.return_value = mock_screenshot_upload

            # Call _do_upload to simulate the full upload process
            sink._do_upload()

            # Verify trace was uploaded (PUT was called)
            assert mock_put.called

            # Find the trace upload call (not screenshot upload)
            # Screenshot uploads happen first, then trace upload
            put_calls = mock_put.call_args_list
            trace_upload_call = None
            for call in put_calls:
                # Trace upload has Content-Type: application/x-gzip
                headers = call[1].get("headers", {})
                if headers.get("Content-Type") == "application/x-gzip":
                    trace_upload_call = call
                    break

            assert trace_upload_call is not None, "Trace upload should have been called"

            # Decompress and verify the uploaded trace data
            compressed_data = trace_upload_call[1]["data"]
            decompressed_data = gzip.decompress(compressed_data)
            trace_content = decompressed_data.decode("utf-8")

            # Parse the trace events
            events = [
                json.loads(line) for line in trace_content.strip().split("\n") if line.strip()
            ]

            # Find snapshot event
            snapshot_events = [e for e in events if e.get("type") == "snapshot"]
            assert len(snapshot_events) > 0, "Should have at least one snapshot event"

            # Verify screenshot_base64 is NOT in the uploaded trace
            for event in snapshot_events:
                data = event.get("data", {})
                assert (
                    "screenshot_base64" not in data
                ), "screenshot_base64 should be removed from uploaded trace"
                assert (
                    "screenshot_format" not in data
                ), "screenshot_format should be removed from uploaded trace"
                # Verify other fields are preserved
                assert "url" in data
                assert "element_count" in data

        # Cleanup
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        trace_path = cache_dir / f"{run_id}.jsonl"
        cleaned_trace_path = cache_dir / f"{run_id}.cleaned.jsonl"
        if trace_path.exists():
            trace_path.unlink()
        if cleaned_trace_path.exists():
            cleaned_trace_path.unlink()
