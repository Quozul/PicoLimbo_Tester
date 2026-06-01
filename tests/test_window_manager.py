"""Unit tests for src/infrastructure/window_manager.py."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.window_manager import WindowManager, parse_window_info


class TestParseWindowInfo:
    """Tests for the pure parse_window_info function."""

    def test_parses_standard_xdotool_output(self):
        text = "Window: 0x1234567\nWidth: 1024\tHeight: 768\nx=0\ty=0"
        result = parse_window_info(text)
        assert result == {"x": 0, "y": 0, "width": 1024, "height": 768}

    def test_parses_with_x_equals_format(self):
        text = "width=1024  height=768\ndepth=24\nx=100     y=200"
        result = parse_window_info(text)
        assert result == {"x": 100, "y": 200, "width": 1024, "height": 768}

    def test_parses_with_tab_separated(self):
        text = "Width: 800\tHeight: 600\nX: 50\tY: 30"
        result = parse_window_info(text)
        assert result == {"x": 50, "y": 30, "width": 800, "height": 600}

    def test_returns_none_for_empty_string(self):
        assert parse_window_info("") is None

    def test_returns_none_for_unparseable_text(self):
        assert parse_window_info("random text without geometry") is None

    def test_returns_none_for_partial_data(self):
        text = "width=1024  height=768\ndepth=24\nx=0"
        result = parse_window_info(text)
        assert result is None

    def test_handles_negative_coordinates(self):
        text = "width=1024  height=768\nx=-10     y=-20"
        result = parse_window_info(text)
        assert result == {"x": -10, "y": -20, "width": 1024, "height": 768}


class TestWindowManagerSearchByName:
    """Tests for WindowManager.search_by_name."""

    def test_returns_first_match(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345678\n87654321\n"
        with patch("subprocess.run", return_value=mock_result) as run_mock:
            result = wm.search_by_name("Minecraft")
        assert result == "12345678"
        run_mock.assert_called_once_with(
            ["xdotool", "search", "--name", "Minecraft"],
            capture_output=True,
            text=True,
        )

    def test_returns_none_on_failure(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = wm.search_by_name("NonExistent")
        assert result is None

    def test_returns_none_on_empty_output(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"
        with patch("subprocess.run", return_value=mock_result):
            result = wm.search_by_name("Minecraft")
        assert result is None


class TestWindowManagerSearchByClass:
    """Tests for WindowManager.search_by_class."""

    def test_returns_last_match(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "11111111\n22222222\n"
        with patch("subprocess.run", return_value=mock_result) as run_mock:
            result = wm.search_by_class("java")
        assert result == "22222222"
        run_mock.assert_called_once_with(
            ["xdotool", "search", "--class", "java"],
            capture_output=True,
            text=True,
        )

    def test_returns_none_on_failure(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = wm.search_by_class("NonExistent")
        assert result is None


class TestWindowManagerGetGeometry:
    """Tests for WindowManager.get_geometry."""

    def test_returns_geometry_dict(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "width=1024  height=768\nx=0     y=0"
        with patch("subprocess.run", return_value=mock_result):
            result = wm.get_geometry("12345678")
        assert result == {"x": 0, "y": 0, "width": 1024, "height": 768}

    def test_returns_none_on_failure(self):
        wm = WindowManager()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = wm.get_geometry("invalid")
        assert result is None


class TestWindowManagerMoveTo:
    """Tests for WindowManager.move_to."""

    def test_calls_xdotool_windowmove(self):
        wm = WindowManager()
        with patch("subprocess.run") as run_mock:
            wm.move_to("12345678", 100, 200)
        run_mock.assert_called_once_with(
            ["xdotool", "windowmove", "12345678", "100", "200"],
            capture_output=True,
        )

    def test_handles_zero_coordinates(self):
        wm = WindowManager()
        with patch("subprocess.run") as run_mock:
            wm.move_to("12345678", 0, 0)
        run_mock.assert_called_once_with(
            ["xdotool", "windowmove", "12345678", "0", "0"],
            capture_output=True,
        )
