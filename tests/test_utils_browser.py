"""
Unit tests for sentience.utils.browser module.

Tests browser storage state saving functionality.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sentience.utils.browser import save_storage_state


class TestSaveStorageState:
    """Tests for save_storage_state function."""

    def test_save_storage_state_creates_file(self):
        """Test that save_storage_state creates a file with storage state."""
        # Create a mock BrowserContext
        mock_context = Mock()
        mock_context.storage_state.return_value = {
            "cookies": [
                {
                    "name": "session_id",
                    "value": "abc123",
                    "domain": "example.com",
                    "path": "/",
                }
            ],
            "origins": [
                {
                    "origin": "https://example.com",
                    "localStorage": [{"name": "user_pref", "value": "dark_mode"}],
                }
            ],
        }

        # Use temporary file
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "storage.json"

            # Call function
            save_storage_state(mock_context, file_path)

            # Verify file was created
            assert file_path.exists()

            # Verify content
            with open(file_path) as f:
                data = json.load(f)

            assert "cookies" in data
            assert "origins" in data
            assert len(data["cookies"]) == 1
            assert data["cookies"][0]["name"] == "session_id"

    def test_save_storage_state_creates_parent_directories(self):
        """Test that save_storage_state creates parent directories if needed."""
        mock_context = Mock()
        mock_context.storage_state.return_value = {"cookies": [], "origins": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested path
            file_path = Path(tmpdir) / "nested" / "deep" / "storage.json"

            # Should not raise error
            save_storage_state(mock_context, file_path)

            # Verify file was created
            assert file_path.exists()
            assert file_path.parent.exists()

    def test_save_storage_state_with_string_path(self):
        """Test that save_storage_state accepts string paths."""
        mock_context = Mock()
        mock_context.storage_state.return_value = {"cookies": [], "origins": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "storage.json")

            save_storage_state(mock_context, file_path)

            assert Path(file_path).exists()

    def test_save_storage_state_calls_context_storage_state(self):
        """Test that save_storage_state calls context.storage_state()."""
        mock_context = Mock()
        mock_context.storage_state.return_value = {"cookies": [], "origins": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "storage.json"

            save_storage_state(mock_context, file_path)

            # Verify storage_state was called
            mock_context.storage_state.assert_called_once()

    def test_save_storage_state_json_format(self):
        """Test that saved file is valid JSON with indentation."""
        mock_context = Mock()
        mock_context.storage_state.return_value = {
            "cookies": [{"name": "test", "value": "value"}],
            "origins": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "storage.json"

            save_storage_state(mock_context, file_path)

            # Verify JSON is valid and formatted
            with open(file_path) as f:
                content = f.read()
                # Should have indentation (contains newlines)
                assert "\n" in content
                # Should be valid JSON
                data = json.loads(content)
                assert isinstance(data, dict)

    def test_save_storage_state_handles_empty_state(self):
        """Test that save_storage_state handles empty storage state."""
        mock_context = Mock()
        mock_context.storage_state.return_value = {"cookies": [], "origins": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "storage.json"

            save_storage_state(mock_context, file_path)

            with open(file_path) as f:
                data = json.load(f)

            assert data == {"cookies": [], "origins": []}

    def test_save_storage_state_prints_success_message(self, capsys):
        """Test that save_storage_state prints success message."""
        mock_context = Mock()
        mock_context.storage_state.return_value = {"cookies": [], "origins": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "storage.json"

            save_storage_state(mock_context, file_path)

            captured = capsys.readouterr()
            assert "✅" in captured.out
            assert "Saved storage state" in captured.out
            assert str(file_path) in captured.out
