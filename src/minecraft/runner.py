"""Minecraft integration test runner with logging."""

import logging
import os
import shutil
import subprocess
import time

from .. import config
from ..infrastructure.minecraft_launcher import MinecraftLauncher
from ..infrastructure.screen_region import ScreenRegionMatcher
from ..infrastructure.window_manager import WindowManager
from ..application.test_service import TestService
from .input import VirtualInputController
from .wait_for import wait_for_screen_region
from PIL import ImageGrab

logger = logging.getLogger(__name__)

REPORTS_DIRECTORY = "integration_tests_reports"

# Shared launcher and window manager instances.
_launcher = MinecraftLauncher(
    game_directory=config.GAME_DIRECTORY,
    jvm_args=config.JVM_ARGS,
    resolution=config.RESOLUTION,
)
_wm = WindowManager()

# Module-level TestService instance for backward-compatible delegation.
_test_service = TestService(
    minecraft=_launcher,
    window_manager=_wm,
    screen_matcher=ScreenRegionMatcher(),
    input_controller=VirtualInputController(),
    screenshots_dir=config.SCREENSHOTS_DIR,
)

# Absolute position of the "Quit Game" button within the 1024x768 game window.
# Computed for the new standard resolution.
_QUIT_REGION_NEWER = config._QUIT_REGION_NEWER
_QUIT_REGION_OLDER = config._QUIT_REGION_OLDER


def _is_lwjgl2_version(version: str) -> bool:
    """LWJGL 2 is used by Minecraft 1.7–1.12; it crashes in fullscreen under Xvfb
    because XRandR returns an empty display-mode list."""
    try:
        major, minor = (int(x) for x in version.split(".")[:2])
        return (major, minor) <= (1, 12)
    except ValueError:
        return False


def click_in_minecraft_window(
    mouse: VirtualInputController,
    absolute_x: int,
    absolute_y: int,
):
    logger.info("  clicking at screen (%d, %d)", absolute_x, absolute_y)
    mouse.move_to(absolute_x, absolute_y)
    time.sleep(0.1)
    mouse.click()
    time.sleep(0.1)


def wait_for_game(version: str) -> str:
    """Wait for Minecraft to load to the main menu and return the window ID."""
    window_id = None
    window_info = None
    deadline = time.time() + 120

    # Keep searching until we find a window whose geometry we can actually read.
    # Older versions (LWJGL 2) create transient splash/init windows that disappear
    # before xdotool can query them, so we need the check inside the loop.
    while time.time() < deadline:
        wid = _wm.search_by_name("Minecraft")
        if not wid:
            wid = _wm.search_by_name("Minecraft*")
        if not wid:
            wid = _wm.search_by_name("Minecraft 1.13")
        if not wid:
            wid = _wm.search_by_class("java")

        if wid:
            info = _wm.get_geometry(wid)
            if info:
                window_id = wid
                window_info = info
                break
        time.sleep(1)

    if not window_id or not window_info:
        raise Exception(f"Could not find a stable window for {version}")

    # LWJGL 2 versions are run windowed to avoid XRandR crashes.
    # Move the window to (0,0) so that window-relative coordinates
    # equal absolute screen coordinates.
    if _is_lwjgl2_version(version):
        _wm.move_to(window_id, 0, 0)
        time.sleep(0.3)

    watch_region = (
        _QUIT_REGION_OLDER if _is_lwjgl2_version(version) else _QUIT_REGION_NEWER
    )

    matched = wait_for_screen_region(
        reference_images_dir="references",
        region=watch_region,
        timeout=15.0,
        interval=0.5,
    )
    if not matched:
        raise Exception(f"Main menu not detected for {version}")

    return window_id


def log_to_multiplayer(
    version: str, virtual_device: VirtualInputController, window_id: str
) -> None:
    window_info = _wm.get_geometry(window_id)
    if not window_info:
        raise Exception(f"Could not get window geometry for {version}")

    logger.info("window info=%s", window_info)

    virtual_device._activate()
    # Click on "Multiplayer" button
    click_in_minecraft_window(virtual_device, *config.CLICK_MULTIPLAYER)
    # Click on server's button
    if version.startswith("1.7."):
        click_in_minecraft_window(virtual_device, *config.CLICK_SERVER_BUTTON_1_7)
    else:
        click_in_minecraft_window(virtual_device, *config.CLICK_SERVER_BUTTON_1_8_PLUS)
    # Click on "Join Server" button
    click_in_minecraft_window(virtual_device, *config.CLICK_JOIN_SERVER)


def start_minecraft(version: str) -> subprocess.Popen:
    """Start Minecraft and return the subprocess.Popen handle.

    Parameters
    ----------
    version : str
        Minecraft version string, e.g. ``"1.20.1"``.

    Returns
    -------
    subprocess.Popen
        Running process handle.
    """
    return _launcher.start(version)


def empty_directory(directory: str) -> None:
    if not os.path.exists(directory):
        return
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            logger.error("Failed to delete %s. Reason: %s", file_path, e)


def capture_screenshot(
    version: str,
    commit_hash: str,
    screenshots_dir: str,
) -> str:
    # Capture the full screen to avoid any cropping from bbox rounding
    # or window-manager effects that can cut off the top of the game window.
    current_image = ImageGrab.grab().convert("RGB")

    os.makedirs(screenshots_dir, exist_ok=True)

    # Include commit hash in the filename so screenshots from different
    # commits don't collide.
    commit_short = commit_hash[:8]
    basename = f"{version}_{commit_short}_screenshot.png"
    dest_path = os.path.join(screenshots_dir, basename)
    current_image.save(dest_path)
    logger.info("Saved screenshot to %s", dest_path)
    return dest_path


def test_single_version(
    version: str,
    commit_hash: str,
    virtual_device: VirtualInputController,
    screenshots_dir: str,
    login_wait_timeout: int = 30,
) -> dict:
    """Test a single Minecraft version. Returns a test result dict.

    Thin wrapper for backward compatibility — delegates to :class:`TestService`.
    The ``virtual_device`` and ``screenshots_dir`` parameters are accepted
    for API compatibility but the service manages its own resources.
    """
    logger.info("--- Starting test for version: %s ---", version)
    test_result = _test_service.test_version(
        version_str=version,
        commit_hash=commit_hash,
        login_wait_timeout=login_wait_timeout,
    )

    result = {
        "version": version,
        "passed": test_result.passed,
        "screenshot_path": str(test_result.screenshot_path) if test_result.screenshot_path else None,
        "duration_seconds": test_result.duration_seconds,
        "error": test_result.error,
    }

    if test_result.passed:
        logger.info("✅ Test PASSED for version: %s", version)
    else:
        logger.error("❌ Test FAILED for version: %s", version)
        logger.error("   Reason: %s", test_result.error)

    return result
