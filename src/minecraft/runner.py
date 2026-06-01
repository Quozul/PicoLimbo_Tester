"""Minecraft integration test runner with logging."""

import logging
import os
import pathlib
import re
import shutil
import subprocess
import time

from .. import config
from ..infrastructure.minecraft_launcher import MinecraftLauncher
from .env import create_servers_dat, create_options_txt
from .input import VirtualInputController
from .wait_for import wait_for_screen_region
from PIL import ImageGrab

logger = logging.getLogger(__name__)

REPORTS_DIRECTORY = "integration_tests_reports"

# Shared launcher instance configured from the module-level config.
_launcher = MinecraftLauncher(
    game_directory=config.GAME_DIRECTORY,
    jvm_args=config.JVM_ARGS,
    resolution=config.RESOLUTION,
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


def parse_window_info(window_text: str) -> dict | None:
    position_match = re.search(r"Position:\s*(\d+),\s*(\d+)", window_text)
    geometry_match = re.search(r"Geometry:\s*(\d+)\s*x\s*(\d+)", window_text)

    if not (position_match and geometry_match):
        return None

    x = int(position_match.group(1))
    y = int(position_match.group(2))
    width = int(geometry_match.group(1))
    height = int(geometry_match.group(2))

    return {"x": x, "y": y, "width": width, "height": height}


def get_minecraft_window() -> str | None:
    for title in ["Minecraft*", "Minecraft", "Minecraft 1.13"]:
        result = subprocess.run(
            ["xdotool", "search", "--name", title], capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]

    result = subprocess.run(
        ["xdotool", "search", "--class", "java"], capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")[-1]

    return None


def get_window_info(window_id: str) -> dict | None:
    result = subprocess.run(
        ["xdotool", "getwindowgeometry", window_id], capture_output=True, text=True
    )
    result = result.stdout.strip()
    return parse_window_info(result)


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
        wid = get_minecraft_window()
        if wid:
            info = get_window_info(wid)
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
        subprocess.run(
            ["xdotool", "windowmove", window_id, "0", "0"], capture_output=True
        )
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
    window_info = get_window_info(window_id)
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
    window_id: str,
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
    """Test a single Minecraft version. Returns a test result dict."""
    logger.info("--- Starting test for version: %s ---", version)
    process = None
    start_time = time.time()
    result = {
        "version": version,
        "passed": False,
        "screenshot_path": None,
        "duration_seconds": None,
        "error": None,
    }

    try:
        process = start_minecraft(version)
        window_id = wait_for_game(version)
        virtual_device.set_window(window_id)
        log_to_multiplayer(version, virtual_device, window_id)
        time.sleep(login_wait_timeout)  # wait for the player to be logged in
        screenshot_path = capture_screenshot(
            version, commit_hash, window_id, screenshots_dir
        )
        result["passed"] = True
        result["screenshot_path"] = screenshot_path
        logger.info("✅ Test PASSED for version: %s", version)
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error("❌ Test FAILED for version: %s", version)
        logger.error("   Reason: %s", e)
        return result
    finally:
        if process:
            logger.info("--- Cleaning up for version: %s ---", version)
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "   Process for %s did not terminate gracefully, killing.", version
                )
                process.kill()
        result["duration_seconds"] = round(time.time() - start_time, 1)
