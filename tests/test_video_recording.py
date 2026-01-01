"""
Tests for video recording functionality
"""

import os
import tempfile
from pathlib import Path

import pytest

from sentience import SentienceBrowser


def test_video_recording_basic():
    """Test basic video recording functionality"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"

        browser = SentienceBrowser(headless=True, record_video_dir=str(video_dir))
        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")

            video_path = browser.close()

            # Verify video was created
            assert video_path is not None
            assert os.path.exists(video_path)
            assert video_path.endswith(".webm")

            # Verify file has content
            file_size = os.path.getsize(video_path)
            assert file_size > 0
        except Exception:
            browser.close()
            raise


def test_video_recording_custom_resolution():
    """Test video recording with custom resolution"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"

        browser = SentienceBrowser(
            headless=True,
            record_video_dir=str(video_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")

            video_path = browser.close()

            assert video_path is not None
            assert os.path.exists(video_path)
        except Exception:
            browser.close()
            raise


def test_video_recording_custom_output_path():
    """Test video recording with custom output path"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"
        custom_path = video_dir / "my_recording.webm"

        browser = SentienceBrowser(headless=True, record_video_dir=str(video_dir))
        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")

            video_path = browser.close(output_path=str(custom_path))

            # Verify video was renamed to custom path
            assert video_path == str(custom_path)
            assert os.path.exists(custom_path)
        except Exception:
            browser.close()
            raise


def test_video_recording_nested_output_path():
    """Test video recording with nested directory in output path"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"
        nested_path = video_dir / "project" / "tutorials" / "video1.webm"

        browser = SentienceBrowser(headless=True, record_video_dir=str(video_dir))
        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")

            video_path = browser.close(output_path=str(nested_path))

            # Verify nested directories were created
            assert video_path == str(nested_path)
            assert os.path.exists(nested_path)
            assert nested_path.parent.exists()
        except Exception:
            browser.close()
            raise


def test_no_video_recording_when_disabled():
    """Test that no video is created when recording is disabled"""
    browser = SentienceBrowser(headless=True)
    browser.start()

    try:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle", timeout=10000)

        video_path = browser.close()

        # Should return None when recording is disabled
        assert video_path is None
    except Exception:
        browser.close()
        raise


def test_video_recording_directory_auto_created():
    """Test that video directory is automatically created"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Use a non-existent directory
        video_dir = Path(temp_dir) / "new_recordings" / "subdir"

        browser = SentienceBrowser(headless=True, record_video_dir=str(video_dir))
        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")

            video_path = browser.close()

            # Verify directory was created
            assert video_dir.exists()
            assert video_path is not None
            assert os.path.exists(video_path)
        except Exception:
            browser.close()
            raise


def test_video_recording_with_pathlib():
    """Test video recording using pathlib.Path objects"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"
        output_path = video_dir / "test_video.webm"

        browser = SentienceBrowser(headless=True, record_video_dir=video_dir)  # Pass Path object
        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")

            video_path = browser.close(output_path=output_path)  # Pass Path object

            assert os.path.exists(output_path)
            assert video_path == str(output_path)
        except Exception:
            browser.close()
            raise


def test_video_recording_multiple_sessions():
    """Test creating multiple video recordings in sequence"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"

        video_paths = []

        # Create 3 video recordings
        for i in range(3):
            browser = SentienceBrowser(headless=True, record_video_dir=str(video_dir))
            browser.start()

            try:
                browser.page.goto("https://example.com")
                browser.page.wait_for_load_state("networkidle", timeout=10000)

                output_path = video_dir / f"video_{i}.webm"
                video_path = browser.close(output_path=str(output_path))
                video_paths.append(video_path)
            except Exception:
                browser.close()
                raise

        # Verify all videos were created
        for video_path in video_paths:
            assert os.path.exists(video_path)


def test_video_recording_default_resolution():
    """Test that default resolution is 1280x800"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"

        browser = SentienceBrowser(headless=True, record_video_dir=str(video_dir))

        # Verify default resolution
        assert browser.record_video_size == {"width": 1280, "height": 800}

        browser.start()

        try:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")
            browser.close()
        except Exception:
            browser.close()
            raise


def test_video_recording_with_context_manager():
    """Test that context manager works when NOT calling close() manually"""
    with tempfile.TemporaryDirectory() as temp_dir:
        video_dir = Path(temp_dir) / "recordings"

        # Use context manager WITHOUT calling close() manually
        with SentienceBrowser(headless=True, record_video_dir=str(video_dir)) as browser:
            browser.page.goto("https://example.com")
            browser.page.wait_for_load_state("domcontentloaded")
            # Don't call browser.close() - let context manager handle it

        # Verify video was created after context manager exits
        # Find the .webm file in the directory
        webm_files = list(video_dir.glob("*.webm"))
        assert len(webm_files) > 0
        assert os.path.exists(webm_files[0])
