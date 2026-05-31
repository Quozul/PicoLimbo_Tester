"""Unit tests for src/minecraft/runner.py helper functions."""

import os
import time

import pytest

from src.minecraft.runner import (
    _is_lwjgl2_version,
    capture_screenshot,
    empty_directory,
    parse_window_info,
)


class TestIsLwjgl2Version:
    """Tests for _is_lwjgl2_version."""

    def test_version_1_7_10(self):
        assert _is_lwjgl2_version("1.7.10") is True

    def test_version_1_8_9(self):
        assert _is_lwjgl2_version("1.8.9") is True

    def test_version_1_9(self):
        assert _is_lwjgl2_version("1.9") is True

    def test_version_1_12_2(self):
        """1.12.2 is the last LWJGL 2 version."""
        assert _is_lwjgl2_version("1.12.2") is True

    def test_version_1_12(self):
        """Boundary: 1.12 is still LWJGL 2."""
        assert _is_lwjgl2_version("1.12") is True

    def test_version_1_13(self):
        """LWJGL 3 starts at 1.13."""
        assert _is_lwjgl2_version("1.13") is False

    def test_version_1_16_5(self):
        assert _is_lwjgl2_version("1.16.5") is False

    def test_version_1_20_1(self):
        assert _is_lwjgl2_version("1.20.1") is False

    def test_version_26_1_2(self):
        assert _is_lwjgl2_version("26.1.2") is False

    def test_invalid_version(self):
        assert _is_lwjgl2_version("abc") is False

    def test_version_with_extra_suffix(self):
        """'1.12.2-extra' splits on '.', takes first two parts (1, 12)."""
        assert _is_lwjgl2_version("1.12.2-extra") is True

    def test_minor_only(self):
        assert _is_lwjgl2_version("1.9") is True


class TestParseWindowInfo:
    """Tests for parse_window_info."""

    def test_valid_input(self):
        result = parse_window_info("Position: 100, 200\nGeometry: 1024x768")
        assert result == {"x": 100, "y": 200, "width": 1024, "height": 768}

    def test_valid_input_different_values(self):
        result = parse_window_info("Position: 0, 0\nGeometry: 1920x1080")
        assert result == {"x": 0, "y": 0, "width": 1920, "height": 1080}

    def test_missing_position(self):
        result = parse_window_info("Geometry: 1024x768")
        assert result is None

    def test_missing_geometry(self):
        result = parse_window_info("Position: 100, 200")
        assert result is None

    def test_garbled_input(self):
        result = parse_window_info("this is not window info at all")
        assert result is None

    def test_empty_string(self):
        result = parse_window_info("")
        assert result is None

    def test_whitespace_around_values(self):
        result = parse_window_info("Position: 50, 150\nGeometry: 800x600")
        assert result == {"x": 50, "y": 150, "width": 800, "height": 600}


class TestEmptyDirectory:
    """Tests for empty_directory."""

    def test_nonexistent_directory(self, tmp_path):
        """Non-existent directory should not raise."""
        nonexistent = str(tmp_path / "does_not_exist")
        empty_directory(nonexistent)  # no exception

    def test_empty_directory(self, tmp_path):
        """Empty directory should not raise."""
        empty_directory(str(tmp_path))  # no exception

    def test_directory_with_files(self, tmp_path):
        """All files should be removed."""
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        empty_directory(str(tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_directory_with_subdirectories(self, tmp_path):
        """Subdirectories and their contents should be removed."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")
        (tmp_path / "top.txt").write_text("top")
        empty_directory(str(tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_directory_with_symlinks(self, tmp_path):
        """Symlinks should be removed (unlinked)."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("real")
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(real_file)
        empty_directory(str(tmp_path))
        assert list(tmp_path.iterdir()) == []


class TestCaptureScreenshot:
    """Tests for capture_screenshot – captures a window via ImageGrab."""

    def test_saves_screenshot_at_window_position(self, tmp_path):
        """Screenshot is saved to screenshots_dir with correct filename."""
        from unittest.mock import MagicMock, patch

        mock_window_info = {"x": 100, "y": 200, "width": 1024, "height": 768}
        screenshots_dir = str(tmp_path / "screenshots")

        # ImageGrab.grab returns a mock image; .convert("RGB") returns
        # mock_image itself so .save() is called on the same object.
        mock_image = MagicMock()
        mock_image.convert.return_value = mock_image

        with (
            patch("src.minecraft.runner.get_window_info", return_value=mock_window_info),
            patch("src.minecraft.runner.ImageGrab.grab", return_value=mock_image),
            patch("os.makedirs"),
        ):
            result_path = capture_screenshot(
                version="1.20.1",
                commit_hash="aabbccdd11223344",
                window_id="fake_window",
                screenshots_dir=screenshots_dir,
            )

        assert "1.20.1" in result_path
        assert "aabbccdd" in result_path
        assert result_path.endswith(".png")

        # Verify ImageGrab was called and .save() was called on the image
        mock_image.save.assert_called_once()
        captured_save_args = mock_image.save.call_args
        assert captured_save_args[0][0] == result_path

    def test_uses_full_screen_capture(self):
        """capture_screenshot uses full screen capture (no window info needed)."""
        from unittest.mock import MagicMock, patch

        mock_image = MagicMock()
        mock_image.convert.return_value = mock_image

        with (
            patch("src.minecraft.runner.ImageGrab.grab", return_value=mock_image),
            patch("os.makedirs"),
        ):
            result_path = capture_screenshot(
                version="1.20.1",
                commit_hash="aabbccdd11223344",
                window_id="fake_window",
                screenshots_dir="/tmp/screenshots",
            )

        # Should save successfully without needing window info
        mock_image.save.assert_called_once()
        assert result_path is not None

    def test_captures_full_screen(self, tmp_path):
        """ImageGrab.grab is called without bbox to capture the full screen."""
        from unittest.mock import MagicMock, patch

        mock_window_info = {"x": 50, "y": 100, "width": 800, "height": 600}
        mock_image = MagicMock()
        screenshots_dir = str(tmp_path / "screenshots")

        with patch("src.minecraft.runner.get_window_info", return_value=mock_window_info):
            with patch("src.minecraft.runner.ImageGrab.grab", return_value=mock_image) as grab_mock:
                with patch("os.makedirs"):
                    capture_screenshot(
                        version="1.19.3",
                        commit_hash="deadbeef",
                        window_id="fake_window",
                        screenshots_dir=screenshots_dir,
                    )

        # ImageGrab.grab is called without bbox to capture full screen
        grab_mock.assert_called_once_with()

    def test_filename_includes_version_and_commit(self, tmp_path):
        """The saved filename contains the version and short commit hash."""
        from unittest.mock import MagicMock, patch

        mock_window_info = {"x": 0, "y": 0, "width": 1024, "height": 768}
        mock_image = MagicMock()
        screenshots_dir = str(tmp_path / "screenshots")

        with (
            patch("src.minecraft.runner.get_window_info", return_value=mock_window_info),
            patch("src.minecraft.runner.ImageGrab.grab", return_value=mock_image),
            patch("os.makedirs"),
        ):
            result_path = capture_screenshot(
                version="26.1.1",
                commit_hash="abcdef1234567890abcdef1234567890abcdef12",
                window_id="fake_window",
                screenshots_dir=screenshots_dir,
            )

        expected_name = "26.1.1_abcdef12_screenshot.png"
        assert os.path.basename(result_path) == expected_name
