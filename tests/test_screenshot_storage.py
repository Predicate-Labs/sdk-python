"""Tests for screenshot storage and upload in CloudTraceSink"""

import base64
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sentience.cloud_tracing import CloudTraceSink
from sentience.models import ScreenshotMetadata


class TestScreenshotStorage:
    """Test screenshot storage functionality in CloudTraceSink."""

    def test_store_screenshot_creates_directory(self):
        """Test that store_screenshot creates screenshot directory."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-1"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Verify directory was created
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        assert screenshot_dir.exists(), "Screenshot directory should be created"

        # Cleanup
        sink.close(blocking=False)
        if screenshot_dir.exists():
            for f in screenshot_dir.glob("step_*"):
                f.unlink()
            screenshot_dir.rmdir()

    def test_store_screenshot_saves_file(self):
        """Test that store_screenshot saves screenshot to file."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-2"

        # Create a test base64 image (1x1 PNG)
        # This is a valid 1x1 PNG in base64
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        test_data_url = f"data:image/png;base64,{test_image_base64}"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Store screenshot
        sink.store_screenshot(
            sequence=1,
            screenshot_data=test_data_url,
            format="png",
            step_id="step_001",
        )

        # Verify file was created
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        screenshot_file = screenshot_dir / "step_0001.png"
        assert screenshot_file.exists(), "Screenshot file should be created"

        # Verify file content
        with open(screenshot_file, "rb") as f:
            file_data = f.read()
        expected_data = base64.b64decode(test_image_base64)
        assert file_data == expected_data, "File content should match decoded base64"

        # Verify metadata was tracked
        assert 1 in sink._screenshot_metadata
        metadata = sink._screenshot_metadata[1]
        assert isinstance(metadata, ScreenshotMetadata)
        assert metadata.sequence == 1
        assert metadata.format == "png"
        assert metadata.step_id == "step_001"
        assert metadata.size_bytes == len(expected_data)

        # Cleanup
        sink.close(blocking=False)
        if screenshot_file.exists():
            screenshot_file.unlink()
        if screenshot_dir.exists():
            screenshot_dir.rmdir()

    def test_store_screenshot_updates_size_counter(self):
        """Test that store_screenshot updates screenshot_total_size_bytes."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-3"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        test_data_url = f"data:image/png;base64,{test_image_base64}"

        sink = CloudTraceSink(upload_url, run_id=run_id)
        initial_size = sink.screenshot_total_size_bytes

        # Store first screenshot
        sink.store_screenshot(sequence=1, screenshot_data=test_data_url, format="png")
        size_after_first = sink.screenshot_total_size_bytes
        assert size_after_first > initial_size

        # Store second screenshot
        sink.store_screenshot(sequence=2, screenshot_data=test_data_url, format="png")
        size_after_second = sink.screenshot_total_size_bytes
        assert size_after_second > size_after_first
        assert size_after_second == size_after_first * 2  # Same image, double size

        # Cleanup
        sink.close(blocking=False)
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        if screenshot_dir.exists():
            for f in screenshot_dir.glob("step_*"):
                f.unlink()
            screenshot_dir.rmdir()

    def test_store_screenshot_handles_jpeg_format(self):
        """Test that store_screenshot handles JPEG format correctly."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-4"

        # Minimal valid JPEG in base64 (1x1 pixel JPEG)
        # This is a valid minimal JPEG file encoded in base64
        test_jpeg_base64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIjLhwcKDcpLDAxNDQ0Hyc5PTgyPC7/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACP/EABQQAQAAAAAAAAAAAAAAAAAAAP/aAAgBAQAAPwCq/9k="
        test_data_url = f"data:image/jpeg;base64,{test_jpeg_base64}"

        sink = CloudTraceSink(upload_url, run_id=run_id)
        sink.store_screenshot(sequence=1, screenshot_data=test_data_url, format="jpeg")

        # Verify file was created with .jpeg extension
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        screenshot_file = screenshot_dir / "step_0001.jpeg"
        assert screenshot_file.exists(), "JPEG screenshot file should be created"

        # Verify metadata format
        metadata = sink._screenshot_metadata[1]
        assert metadata.format == "jpeg"

        # Cleanup
        sink.close(blocking=False)
        if screenshot_file.exists():
            screenshot_file.unlink()
        if screenshot_dir.exists():
            screenshot_dir.rmdir()

    def test_store_screenshot_handles_base64_without_prefix(self):
        """Test that store_screenshot handles base64 without data URL prefix."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-5"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        sink = CloudTraceSink(upload_url, run_id=run_id)
        sink.store_screenshot(sequence=1, screenshot_data=test_image_base64, format="png")

        # Verify file was created
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        screenshot_file = screenshot_dir / "step_0001.png"
        assert screenshot_file.exists()

        # Cleanup
        sink.close(blocking=False)
        if screenshot_file.exists():
            screenshot_file.unlink()
        if screenshot_dir.exists():
            screenshot_dir.rmdir()

    def test_store_screenshot_raises_error_when_closed(self):
        """Test that store_screenshot raises error when sink is closed."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-6"

        sink = CloudTraceSink(upload_url, run_id=run_id)
        sink.close()

        test_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        with pytest.raises(RuntimeError, match="CloudTraceSink is closed"):
            sink.store_screenshot(sequence=1, screenshot_data=test_data_url, format="png")

    def test_store_screenshot_handles_errors_gracefully(self, capsys):
        """Test that store_screenshot handles errors gracefully without crashing."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-storage-7"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Try to store invalid base64 (should not crash)
        invalid_data = "invalid_base64_data!!!"
        sink.store_screenshot(sequence=1, screenshot_data=invalid_data, format="png")

        # Verify error was logged but didn't crash
        captured = capsys.readouterr()
        assert "⚠️" in captured.out or "Failed" in captured.out

        # Cleanup
        sink.close(blocking=False)


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

        with patch("sentience.cloud_tracing.requests.post") as mock_post:
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

        with patch("sentience.cloud_tracing.requests.post") as mock_post:
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

        # Create test screenshots
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        test_data_url = f"data:image/png;base64,{test_image_base64}"

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)

        # Store two screenshots
        sink.store_screenshot(sequence=1, screenshot_data=test_data_url, format="png")
        sink.store_screenshot(sequence=2, screenshot_data=test_data_url, format="png")

        # Mock gateway and upload responses
        mock_upload_urls = {
            "1": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0001.png?signature=...",
            "2": "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/screenshots/step_0002.png?signature=...",
        }

        with (
            patch("sentience.cloud_tracing.requests.post") as mock_post,
            patch("sentience.cloud_tracing.requests.put") as mock_put,
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
            sink._upload_screenshots()

            # Verify gateway was called
            assert mock_post.called

            # Verify uploads were called (2 screenshots)
            assert mock_put.call_count == 2

            # Verify upload URLs and content
            put_calls = mock_put.call_args_list
            assert mock_upload_urls["1"] in [call[0][0] for call in put_calls]
            assert mock_upload_urls["2"] in [call[0][0] for call in put_calls]

        # Cleanup
        sink.close(blocking=False)
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        if screenshot_dir.exists():
            for f in screenshot_dir.glob("step_*"):
                f.unlink()
            screenshot_dir.rmdir()

    def test_upload_screenshots_skips_when_no_screenshots(self, capsys):
        """Test that _upload_screenshots skips when no screenshots stored."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-upload-4"

        sink = CloudTraceSink(upload_url, run_id=run_id)

        # Call upload with no screenshots (should do nothing)
        sink._upload_screenshots()

        # Verify no errors
        captured = capsys.readouterr()
        assert "Uploading" not in captured.out

        sink.close(blocking=False)

    def test_cleanup_files_deletes_screenshots_on_success(self):
        """Test that _cleanup_files deletes screenshot directory on successful upload."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-cleanup-1"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        test_data_url = f"data:image/png;base64,{test_image_base64}"

        sink = CloudTraceSink(upload_url, run_id=run_id)
        sink.store_screenshot(sequence=1, screenshot_data=test_data_url, format="png")

        # Mark as successful and cleanup
        sink._upload_successful = True
        sink._cleanup_files()

        # Verify screenshot directory was deleted
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        assert not screenshot_dir.exists(), "Screenshot directory should be deleted after cleanup"

        sink.close(blocking=False)

    def test_complete_trace_includes_screenshot_count(self):
        """Test that _complete_trace includes screenshot_count in stats."""
        upload_url = "https://sentience.nyc3.digitaloceanspaces.com/user123/run456/trace.jsonl.gz"
        run_id = "test-screenshot-complete-1"
        api_key = "sk_test_123"

        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        test_data_url = f"data:image/png;base64,{test_image_base64}"

        sink = CloudTraceSink(upload_url, run_id=run_id, api_key=api_key)
        sink.store_screenshot(sequence=1, screenshot_data=test_data_url, format="png")
        sink.store_screenshot(sequence=2, screenshot_data=test_data_url, format="png")

        with patch("sentience.cloud_tracing.requests.post") as mock_post:
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
        cache_dir = Path.home() / ".sentience" / "traces" / "pending"
        screenshot_dir = cache_dir / f"{run_id}_screenshots"
        if screenshot_dir.exists():
            for f in screenshot_dir.glob("step_*"):
                f.unlink()
            screenshot_dir.rmdir()
