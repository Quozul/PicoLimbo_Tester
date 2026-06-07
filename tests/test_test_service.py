"""Unit tests for src/application/test_service.py — TestService domain service."""

import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.test_service import TestContext, TestService
from src.domain.value_objects import TestResult
from src.versions import Version


# Mock time.sleep to avoid long waits in tests
def _mock_sleep(seconds):
    pass


@pytest.fixture(autouse=True)
def mock_sleep(monkeypatch):
    """Mock time.sleep globally to avoid long waits in tests."""
    monkeypatch.setattr(time, "sleep", _mock_sleep)


@pytest.fixture
def screenshots_dir(tmp_path):
    return tmp_path / "screenshots"


@pytest.fixture
def mock_minecraft():
    mock = MagicMock()
    mock.get_command.return_value = ["java", "-jar", "minecraft.jar"]
    return mock


@pytest.fixture
def mock_wm(screenshots_dir):
    mock = MagicMock()
    mock.search_by_name.return_value = "12345"
    mock.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}
    return mock


@pytest.fixture
def mock_screen():
    mock = MagicMock()
    mock.wait_for_region.return_value = True
    return mock


@pytest.fixture
def mock_input():
    return MagicMock()


@pytest.fixture
def service(mock_minecraft, mock_wm, mock_screen, mock_input, screenshots_dir):
    return TestService(
        minecraft=mock_minecraft,
        window_manager=mock_wm,
        screen_matcher=mock_screen,
        input_controller=mock_input,
        screenshots_dir=screenshots_dir,
    )


# ── test_version ──────────────────────────────────────────────────────────────


class TestTestVersion:
    """Tests for the main test_version() method."""

    def test_returns_passed_result_on_success(self, screenshots_dir):
        """Test service returns passed result when everything succeeds."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        mock_minecraft = MagicMock()
        mock_minecraft.get_command.return_value = ["java", "-jar", "minecraft.jar"]

        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"

        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        service = TestService(
            minecraft=mock_minecraft,
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        with patch("subprocess.Popen", return_value=mock_process):
            result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is True
        assert result.version == Version.from_string("1.21.1")
        assert result.error is None
        mock_minecraft.get_command.assert_called_once_with("1.21.1")

    def test_returns_failed_result_on_error(self, service):
        """Test service returns failed result when an exception occurs."""
        mock_minecraft = MagicMock()
        mock_minecraft.get_command.side_effect = RuntimeError("Failed to start")

        service = TestService(
            minecraft=mock_minecraft,
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=Path("/tmp/screenshots"),
        )

        result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is False
        assert "Failed to start" in result.error
        assert result.version == Version.from_string("1.21.1")

    def test_returns_failed_result_when_window_not_found(self, screenshots_dir):
        """Test service returns failed result when window cannot be found."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = None
        mock_wm.search_by_class.return_value = None

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        with patch("subprocess.Popen", return_value=mock_process), \
             patch("time.time", side_effect=[1000, 1121]):
            result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is False
        assert "Minecraft window not found" in result.error

    def test_calls_minecraft_get_command(self, service):
        """Test service calls get_command with the version string."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        with patch("subprocess.Popen", return_value=mock_process):
            service.test_version("1.20.1", "deadbeef")

        service._minecraft.get_command.assert_called_once_with("1.20.1")

    def test_calls_input_set_window(self, service):
        """Test service sets the window on the input controller."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        with patch("subprocess.Popen", return_value=mock_process):
            service.test_version("1.21.1", "abc123def456")

        service._input.set_window.assert_called_once_with("12345")

    def test_calls_input_click(self, service):
        """Test service clicks multiplayer button coordinates."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        with patch("subprocess.Popen", return_value=mock_process):
            service.test_version("1.21.1", "abc123def456")

        service._input.click.assert_called()
        assert service._input.click.call_count == 3

    def test_calls_cleanup_on_success(self, service):
        """Test service cleans up process on success."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is True
        mock_process.terminate.assert_called_once()

    def test_calls_cleanup_on_failure(self, screenshots_dir):
        """Test service cleans up process on failure."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = None
        mock_wm.search_by_class.return_value = None

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        with patch("subprocess.Popen", return_value=mock_process), \
             patch("time.time", side_effect=[1000, 1121]):
            result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is False
        mock_process.terminate.assert_called_once()


# ── _wait_for_game ────────────────────────────────────────────────────────────


class TestWaitForGame:
    """Tests for the _wait_for_game() helper method."""

    def test_finds_window_by_name(self, screenshots_dir):
        """Wait for game finds window by name."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        window_id = service._wait_for_game(Version.from_string("1.21.1"))

        assert window_id == "12345"
        mock_wm.search_by_name.assert_called_once_with("Minecraft")

    def test_falls_back_to_class_name(self, screenshots_dir):
        """Wait for game falls back to window class name."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = None
        mock_wm.search_by_class.return_value = "54321"
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        window_id = service._wait_for_game(Version.from_string("1.21.1"))

        assert window_id == "54321"
        mock_wm.search_by_class.assert_called_once_with("java")

    def test_moves_lwjgl2_window_to_origin(self, screenshots_dir):
        """Wait for game moves LWJGL2 window to (0, 0)."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._wait_for_game(Version.from_string("1.8.9"))

        mock_wm.move_to.assert_called_once_with("12345", 0, 0)

    def test_does_not_move_lwjgl3_window(self, screenshots_dir):
        """Wait for game does not move LWJGL3 window."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._wait_for_game(Version.from_string("1.21.1"))

        mock_wm.move_to.assert_not_called()

    def test_waits_for_quit_button_region(self, screenshots_dir):
        """Wait for game waits for the quit button region."""
        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._wait_for_game(Version.from_string("1.21.1"))

        mock_screen.wait_for_region.assert_called_once()
        call_args = mock_screen.wait_for_region.call_args
        assert call_args[0][0] == "quit_button"
        assert call_args[1]["timeout"] == 15.0


# ── _get_quit_region ──────────────────────────────────────────────────────────


class TestGetQuitRegion:
    """Tests for the _get_quit_region() helper method."""

    def test_returns_newer_for_1_14_plus(self, screenshots_dir):
        """Get quit region returns newer region for 1.14+."""
        from src.config import _QUIT_REGION_NEWER

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        region = service._get_quit_region(Version.from_string("1.14.0"))
        assert region == _QUIT_REGION_NEWER

    def test_returns_newer_for_1_21(self, screenshots_dir):
        """Get quit region returns newer region for 1.21."""
        from src.config import _QUIT_REGION_NEWER

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        region = service._get_quit_region(Version.from_string("1.21.1"))
        assert region == _QUIT_REGION_NEWER

    def test_returns_older_for_1_13_and_below(self, screenshots_dir):
        """Get quit region returns older region for 1.13 and below."""
        from src.config import _QUIT_REGION_OLDER

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        region = service._get_quit_region(Version.from_string("1.13.2"))
        assert region == _QUIT_REGION_OLDER

    def test_returns_older_for_1_7(self, screenshots_dir):
        """Get quit region returns older region for 1.7."""
        from src.config import _QUIT_REGION_OLDER

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        region = service._get_quit_region(Version.from_string("1.7.10"))
        assert region == _QUIT_REGION_OLDER


# ── _get_multiplayer_click ────────────────────────────────────────────────────


class TestGetMultiplayerClick:
    """Tests for the _get_multiplayer_click() helper method."""

    def test_returns_1_7_coords_for_1_7(self, screenshots_dir):
        """Get multiplayer click returns 1.7 coords for 1.7."""
        from src.config import CLICK_SERVER_BUTTON_1_7

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        click = service._get_multiplayer_click(Version.from_string("1.7.10"))
        assert click == CLICK_SERVER_BUTTON_1_7

    def test_returns_1_8_coords_for_1_8(self, screenshots_dir):
        """Get multiplayer click returns 1.8 coords for 1.8."""
        from src.config import CLICK_SERVER_BUTTON_1_8_PLUS

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        click = service._get_multiplayer_click(Version.from_string("1.8.9"))
        assert click == CLICK_SERVER_BUTTON_1_8_PLUS

    def test_returns_1_8_coords_for_1_21(self, screenshots_dir):
        """Get multiplayer click returns 1.8+ coords for 1.21."""
        from src.config import CLICK_SERVER_BUTTON_1_8_PLUS

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )
        click = service._get_multiplayer_click(Version.from_string("1.21.1"))
        assert click == CLICK_SERVER_BUTTON_1_8_PLUS


# ── _capture_screenshot ───────────────────────────────────────────────────────


class TestCaptureScreenshot:
    """Tests for the _capture_screenshot() helper method."""

    def test_saves_file_with_window_geometry(self, tmp_path, screenshots_dir):
        """Capture screenshot saves file when window geometry is available."""
        mock_wm = MagicMock()
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}

        mock_image = MagicMock()

        # Use side_effect so the actual file gets created on disk
        def _save_side_effect(path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"fake screenshot")

        mock_image.save.side_effect = _save_side_effect

        with patch("pyscreenshot.grab", return_value=mock_image):
            service = TestService(
                minecraft=MagicMock(),
                window_manager=mock_wm,
                screen_matcher=MagicMock(),
                input_controller=MagicMock(),
                screenshots_dir=screenshots_dir,
            )

            result = service._capture_screenshot(
                Version.from_string("1.21.1"),
                "abc123def456",
                "12345",
            )

        assert result is not None
        assert result.exists()
        mock_image.save.assert_called_once()

    def test_returns_none_on_failure(self, tmp_path, screenshots_dir):
        """Capture screenshot returns None when pyscreenshot fails."""
        with patch("pyscreenshot.grab", side_effect=Exception("Failed")):
            service = TestService(
                minecraft=MagicMock(),
                window_manager=MagicMock(),
                screen_matcher=MagicMock(),
                input_controller=MagicMock(),
                screenshots_dir=screenshots_dir,
            )

            result = service._capture_screenshot(
                Version.from_string("1.21.1"),
                "abc123def456",
                "12345",
            )

        assert result is None

    def test_returns_none_when_no_window_id(self, screenshots_dir):
        """Capture screenshot returns None when no window ID is provided."""
        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        result = service._capture_screenshot(
            Version.from_string("1.21.1"),
            "abc123def456",
            None,
        )

        assert result is None

    def test_creates_commit_hash_subdirectory(self, tmp_path, screenshots_dir):
        """Capture screenshot creates a subdirectory named after the commit hash."""
        mock_wm = MagicMock()
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}

        mock_image = MagicMock()
        mock_image.save = MagicMock()

        with patch("pyscreenshot.grab", return_value=mock_image):
            service = TestService(
                minecraft=MagicMock(),
                window_manager=mock_wm,
                screen_matcher=MagicMock(),
                input_controller=MagicMock(),
                screenshots_dir=screenshots_dir,
            )

            service._capture_screenshot(
                Version.from_string("1.21.1"),
                "abc123def4567890",
                "12345",
            )

        # The subdirectory should be named after the first 8 chars of the commit hash
        expected_dir = screenshots_dir / "abc123de"
        assert expected_dir.exists()


# ── _cleanup ──────────────────────────────────────────────────────────────────


class TestCleanup:
    """Tests for the _cleanup() helper method."""

    def test_terminates_running_process(self, screenshots_dir):
        """Cleanup terminates a running process."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None

        context = TestContext(process=mock_process)

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._cleanup(context)

        mock_process.terminate.assert_called_once()

    def test_kills_process_on_timeout(self, screenshots_dir):
        """Cleanup kills process if terminate times out."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)

        context = TestContext(process=mock_process)

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._cleanup(context)

        mock_process.kill.assert_called_once()

    def test_does_not_terminate_finished_process(self, screenshots_dir):
        """Cleanup does not terminate an already-finished process."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Already finished

        context = TestContext(process=mock_process)

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._cleanup(context)

        mock_process.terminate.assert_not_called()

    def test_does_nothing_with_none_process(self, screenshots_dir):
        """Cleanup does nothing when process is None."""
        context = TestContext(process=None)

        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._cleanup(context)  # Should not raise

    def test_does_nothing_with_none_context(self, screenshots_dir):
        """Cleanup does nothing when context is None."""
        service = TestService(
            minecraft=MagicMock(),
            window_manager=MagicMock(),
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        service._cleanup(None)  # Should not raise


# ── _get_screenshot_bbox ──────────────────────────────────────────────────────


class TestGetScreenshotBbox:
    """Tests for the _get_screenshot_bbox() helper method."""

    def test_returns_bbox_from_geometry(self, screenshots_dir):
        """Get screenshot bbox returns correct bbox from window geometry."""
        mock_wm = MagicMock()
        mock_wm.get_geometry.return_value = {
            "x": 100,
            "y": 200,
            "width": 1024,
            "height": 768,
        }

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        bbox = service._get_screenshot_bbox("12345")

        assert bbox == (100, 200, 1124, 968)

    def test_returns_none_for_no_window_id(self, screenshots_dir):
        """Get screenshot bbox returns None when no window ID."""
        mock_wm = MagicMock()

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        bbox = service._get_screenshot_bbox(None)

        assert bbox is None

    def test_returns_none_when_geometry_missing(self, screenshots_dir):
        """Get screenshot bbox returns None when geometry is None."""
        mock_wm = MagicMock()
        mock_wm.get_geometry.return_value = None

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=MagicMock(),
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        bbox = service._get_screenshot_bbox("12345")

        assert bbox is None


# ── Integration: test_version end-to-end ──────────────────────────────────────


class TestTestVersionIntegration:
    """Integration-style tests for test_version with mocked dependencies."""

    def test_full_flow_with_mocked_process(self, screenshots_dir):
        """Test service runs full flow with mocked process."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_wm.get_geometry.return_value = {"x": 0, "y": 0, "width": 1024, "height": 768}

        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        mock_input = MagicMock()

        mock_minecraft = MagicMock()
        mock_minecraft.get_command.return_value = ["java", "-jar", "minecraft.jar"]

        service = TestService(
            minecraft=mock_minecraft,
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=mock_input,
            screenshots_dir=screenshots_dir,
        )

        with patch("subprocess.Popen", return_value=mock_process):
            result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is True
        assert result.version == Version.from_string("1.21.1")
        assert result.error is None

        # Verify the flow
        mock_minecraft.get_command.assert_called_once_with("1.21.1")
        mock_wm.search_by_name.assert_called_once_with("Minecraft")
        mock_input.set_window.assert_called_once_with("12345")
        mock_input.click.assert_called()
        assert mock_input.click.call_count == 3
        mock_process.terminate.assert_called_once()

        assert result.passed is True
        assert result.version == Version.from_string("1.21.1")
        assert result.error is None

        # Verify the flow
        mock_minecraft.get_command.assert_called_once_with("1.21.1")
        mock_wm.search_by_name.assert_called_once_with("Minecraft")
        mock_input.set_window.assert_called_once_with("12345")
        mock_input.click.assert_called()
        assert mock_input.click.call_count == 3
        mock_process.terminate.assert_called_once()

    def test_version_1_7_10_uses_older_quit_region(self, screenshots_dir):
        """Test service uses older quit region for 1.7.10."""
        from src.config import _QUIT_REGION_OLDER

        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        with patch("subprocess.Popen", return_value=mock_process):
            result = service.test_version("1.7.10", "abc123def456")

        assert result.passed is True

        # Verify older quit region was used
        call_args = mock_screen.wait_for_region.call_args
        assert call_args[0][1] == _QUIT_REGION_OLDER

    def test_version_1_21_1_uses_newer_quit_region(self, screenshots_dir):
        """Test service uses newer quit region for 1.21.1."""
        from src.config import _QUIT_REGION_NEWER

        mock_wm = MagicMock()
        mock_wm.search_by_name.return_value = "12345"
        mock_screen = MagicMock()
        mock_screen.wait_for_region.return_value = True

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = None
        mock_process.stderr = None

        service = TestService(
            minecraft=MagicMock(),
            window_manager=mock_wm,
            screen_matcher=mock_screen,
            input_controller=MagicMock(),
            screenshots_dir=screenshots_dir,
        )

        with patch("subprocess.Popen", return_value=mock_process):
            result = service.test_version("1.21.1", "abc123def456")

        assert result.passed is True

        # Verify newer quit region was used
        call_args = mock_screen.wait_for_region.call_args
        assert call_args[0][1] == _QUIT_REGION_NEWER
