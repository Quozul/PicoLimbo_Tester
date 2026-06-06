"""Test service — domain service for testing Minecraft versions.

Orchestrates MinecraftLauncher, WindowManager, ScreenRegionMatcher, and
VirtualInputController to test a single version of PicoLimbo.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from src.domain.value_objects import TestResult, Version
from src.infrastructure.minecraft_launcher import MinecraftLauncher
from src.infrastructure.screen_region import ScreenRegionMatcher
from src.infrastructure.window_manager import WindowManager
from src.minecraft.input import VirtualInputController
from src.versions import VersionSupport

__all__ = ["TestService", "TestContext"]


@dataclass
class TestContext:
    """Context for a test session."""

    __test__ = False  # pyright: ignore[reportGeneralTypeIssues]

    process: subprocess.Popen | None = None
    window_id: str | None = None


class TestService:
    """Domain service for testing Minecraft versions.

    Uses :class:`MinecraftLauncher`, :class:`WindowManager`,
    :class:`ScreenRegionMatcher`, and :class:`VirtualInputController`
    to test a single version of PicoLimbo.

    Parameters
    ----------
    minecraft : MinecraftLauncher
        Launcher adapter for minecraft_launcher_lib.
    window_manager : WindowManager
        Window manager adapter for xdotool.
    screen_matcher : ScreenRegionMatcher
        Screen region matcher for detecting UI elements.
    input_controller : VirtualInputController
        Virtual input controller for mouse/keyboard automation.
    screenshots_dir : Path
        Directory where screenshots are saved.
    """

    __test__ = False  # pyright: ignore[reportGeneralTypeIssues]

    def __init__(
        self,
        minecraft: MinecraftLauncher,
        window_manager: WindowManager,
        screen_matcher: ScreenRegionMatcher,
        input_controller: VirtualInputController,
        screenshots_dir: Path,
    ) -> None:
        self._minecraft = minecraft
        self._wm = window_manager
        self._screen = screen_matcher
        self._input = input_controller
        self._screenshots_dir = screenshots_dir
        self._version_support = VersionSupport()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_version(
        self,
        version_str: str,
        commit_hash: str,
        login_wait_timeout: int = 30,
    ) -> TestResult:
        """Test a single Minecraft version.

        Parameters
        ----------
        version_str : str
            Minecraft version string (e.g. ``"1.21.1"``).
        commit_hash : str
            Commit hash being tested (used in screenshot filenames).
        login_wait_timeout : int
            Timeout in seconds for waiting for the player to log in.

        Returns
        -------
        TestResult
            Contains pass/fail status, screenshot path, and error details.
        """
        version = Version.from_string(version_str)
        context = TestContext()

        try:
            # Start Minecraft
            cmd = self._minecraft.get_command(version_str)
            context.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )

            # Wait for game window and position it
            window_id = self._wait_for_game(version)
            context.window_id = window_id

            # Set window and navigate to multiplayer
            self._input.set_window(window_id)
            self._log_to_multiplayer(version)

            # Wait for server to be ready
            time.sleep(login_wait_timeout)

            # Capture screenshot
            screenshot_path = self._capture_screenshot(
                version, commit_hash, context.window_id
            )

            return TestResult(
                version=version,
                passed=True,
                screenshot_path=screenshot_path,
            )

        except Exception as e:
            return TestResult(
                version=version,
                passed=False,
                error=str(e),
            )
        finally:
            self._cleanup(context)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_game(self, version: Version) -> str:
        """Wait for Minecraft main menu.

        Returns the window ID of the Minecraft window.

        Raises
        ------
        RuntimeError
            If the Minecraft window cannot be found.
        """
        # Find the window
        window_id = self._wm.search_by_name("Minecraft")
        if window_id is None:
            window_id = self._wm.search_by_class("Minecraft")
        if window_id is None:
            raise RuntimeError(f"Minecraft window not found for version {version}")

        # Position window for LWJGL2 versions
        if self._version_support.is_lwjgl2(version):
            self._wm.move_to(window_id, 0, 0)

        # Wait for quit button region to appear
        quit_region = self._get_quit_region(version)
        self._screen.wait_for_region("quit_button", quit_region, timeout=15.0)

        return window_id

    def _log_to_multiplayer(self, version: Version) -> None:
        """Navigate to multiplayer menu."""
        click = self._get_multiplayer_click(version)
        self._input.click(click[0], click[1])

    def _capture_screenshot(
        self,
        version: Version,
        commit_hash: str,
        window_id: str | None,
    ) -> Path | None:
        """Capture a screenshot of the game.

        Parameters
        ----------
        version : Version
            The Minecraft version being tested.
        commit_hash : str
            Commit hash used for screenshot directory naming.
        window_id : str | None
            Window ID (unused; full screen capture is used).

        Returns
        -------
        Path | None
            Path to the saved screenshot, or ``None`` on failure.
        """
        try:
            import pyscreenshot as ImageGrab  # type: ignore[import-not-found]

            bbox = self._get_screenshot_bbox(window_id)
            if bbox:
                screenshot = ImageGrab.grab(bbox=bbox)
                screenshot_dir = self._screenshots_dir / commit_hash[:8]
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = screenshot_dir / f"screenshot_{version}.png"
                screenshot.save(str(screenshot_path))
                return screenshot_path
        except Exception:
            pass
        return None

    def _cleanup(self, context: TestContext | None) -> None:
        """Clean up test resources (terminate Minecraft process)."""
        if context and context.process and context.process.poll() is None:
            context.process.terminate()
            try:
                context.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                context.process.kill()

    def _get_quit_region(self, version: Version) -> tuple[int, int, int, int]:
        """Get the quit button region for a version.

        Returns the newer region for 1.14+ and the older region for 1.13 and below.
        """
        from src.config import _QUIT_REGION_NEWER, _QUIT_REGION_OLDER

        if version >= Version.from_string("1.14.0"):
            return _QUIT_REGION_NEWER
        return _QUIT_REGION_OLDER

    def _get_multiplayer_click(self, version: Version) -> tuple[int, int]:
        """Get the multiplayer menu click coordinates.

        Returns coordinates for 1.7.x servers (different UI layout)
        or 1.8+ servers.
        """
        from src.config import (
            CLICK_SERVER_BUTTON_1_7,
            CLICK_SERVER_BUTTON_1_8_PLUS,
        )

        if version < Version.from_string("1.8.0"):
            return CLICK_SERVER_BUTTON_1_7
        return CLICK_SERVER_BUTTON_1_8_PLUS

    def _get_screenshot_bbox(
        self, window_id: str | None
    ) -> tuple[int, int, int, int] | None:
        """Get the screenshot bounding box from window geometry.

        Parameters
        ----------
        window_id : str | None
            Window ID to query.

        Returns
        -------
        tuple[int, int, int, int] | None
            ``(x, y, x + width, y + height)`` or ``None`` if the
            window geometry cannot be retrieved.
        """
        if window_id:
            geometry = self._wm.get_geometry(window_id)
            if geometry:
                return (
                    geometry["x"],
                    geometry["y"],
                    geometry["x"] + geometry["width"],
                    geometry["y"] + geometry["height"],
                )
        return None
