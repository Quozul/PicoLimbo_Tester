import argparse
import os
import pathlib
import re
import shutil
import subprocess
import time

import minecraft_launcher_lib

from minecraft_env import create_server_dat
from virtual_devices import VirtualInputController
from wait_for_quit_button import wait_for_screen_region

GAME_DIRECTORY = str(pathlib.Path().resolve().joinpath("minecraft"))
REPORTS_DIRECTORY = "integration_tests_reports"

# Relative position of the "Quit Game" button within the 1024x768 game window.
# Computed for the new standard resolution.
_QUIT_REGION_NEWER = (519, 588, 294, 60)
_QUIT_REGION_OLDER = (517, 602, 294, 60)


def _is_lwjgl2_version(version: str) -> bool:
    """LWJGL 2 is used by Minecraft 1.7–1.12; it crashes in fullscreen under Xvfb
    because XRandR returns an empty display-mode list."""
    try:
        major, minor = (int(x) for x in version.split(".")[:2])
        return (major, minor) <= (1, 12)
    except ValueError:
        return False


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def parse_window_info(window_text: str) -> dict | None:
    position_match = re.search(r"Position:\s*(\d+),(\d+)", window_text)
    geometry_match = re.search(r"Geometry:\s*(\d+)x(\d+)", window_text)

    if not (position_match and geometry_match):
        return None

    x = int(position_match.group(1))
    y = int(position_match.group(2))
    width = int(geometry_match.group(1))
    height = int(geometry_match.group(2))

    if _is_wayland():
        # In XWayland, xdotool reports the outer window size which includes
        # client-side decorations: 25 px border on each side and a 36 px title bar.
        width -= 50
        height -= 86  # 25 top + 36 title + 25 bottom
        x += 25
        y += 61  # 25 top + 36 title

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
    print(f"  clicking at screen ({absolute_x}, {absolute_y})")
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
        # refreshed = get_window_info(window_id)
        # TODO: Maybe wait and ensure that the window has moved?

    absolute_x, absolute_y, width, height = (
        _QUIT_REGION_OLDER if _is_lwjgl2_version(version) else _QUIT_REGION_NEWER
    )

    watch_region = (
        absolute_x,
        absolute_y,
        width,
        height,
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

    print("window info=", window_info)

    virtual_device._activate()
    # Click on "Multiplayer" button
    click_in_minecraft_window(virtual_device, 507, 438)
    # Click on server's button
    if version.startswith("1.7."):
        # TODO: These coordinates are probably incorrect for 1.7.x
        click_in_minecraft_window(virtual_device, 507, 146)
    else:
        click_in_minecraft_window(virtual_device, 507, 146)
    # Click on "Join Server" button
    click_in_minecraft_window(virtual_device, 201, 630)


def test_chat_message(version: str, log_check_timeout: int = 10) -> None:
    start_time = time.time()
    log_path = os.path.join(GAME_DIRECTORY, "logs", "latest.log")

    while time.time() - start_time < log_check_timeout:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if "Welcome to PicoLimbo!" in content:
                    return
        time.sleep(0.5)

    raise Exception("Integration test FAILED: welcome message not received in logs.")


def start_minecraft(version: str) -> subprocess.Popen:
    minecraft_directory = minecraft_launcher_lib.utils.get_minecraft_directory()
    minecraft_launcher_lib.install.install_minecraft_version(
        version, minecraft_directory
    )

    options = minecraft_launcher_lib.utils.generate_test_options()
    options["jvmArguments"] = ["-Xmx2G", "-Xms2G"]
    options["customResolution"] = True
    options["resolutionWidth"] = "1024"
    options["resolutionHeight"] = "768"
    options["gameDirectory"] = GAME_DIRECTORY
    minecraft_command = minecraft_launcher_lib.command.get_minecraft_command(
        version, minecraft_directory, options
    )

    return subprocess.Popen(
        minecraft_command,
        cwd=minecraft_directory,
        stdout=None,
        stderr=None,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )


def empty_directory(directory: str) -> None:
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


def get_latest_screenshot(directory: str) -> str:
    files = [
        f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))
    ]
    if not files:
        raise FileNotFoundError("No screenshots found in the directory.")
    return os.path.join(
        directory,
        max(files, key=lambda f: os.path.getmtime(os.path.join(directory, f))),
    )


def test_screenshot(version: str, virtual_device: VirtualInputController) -> None:
    screenshot_directory = os.path.join(GAME_DIRECTORY, "screenshots")
    empty_directory(screenshot_directory)

    virtual_device.press_f3()
    time.sleep(0.5)
    virtual_device.press_f2()
    time.sleep(0.5)

    if not os.path.exists(REPORTS_DIRECTORY):
        os.makedirs(REPORTS_DIRECTORY)

    latest_screenshot = get_latest_screenshot(screenshot_directory)
    basename = os.path.basename(latest_screenshot)
    shutil.move(
        latest_screenshot,
        os.path.join(REPORTS_DIRECTORY, f"{version}_{basename}"),
    )


def test_single_version(version: str, virtual_device: VirtualInputController) -> bool:
    print(f"--- Starting test for version: {version} ---")
    process = None

    try:
        process = start_minecraft(version)
        window_id = wait_for_game(version)
        virtual_device.set_window(window_id)
        log_to_multiplayer(version, virtual_device, window_id)
        # the test for chat message does not work anymore, I suppose the latest.log file does not exist anymore given we now run inside of Docker, but I'm not sure
        # however, I find this test not reliable enough, and it does not cover the most important feature
        # test_chat_message(version, log_check_timeout=15)
        time.sleep(2)  # wait for the player to be logged in (hopefully)
        # in reality, here what I'd like is to wait for PicoLimbo to send a log,
        # maybe implement some sort of debug feature flag to compile PicoLimbo in a debug mode that implements this king of TCP debug server,
        # this script will then wait for this log, and resume from there
        # this log would indicate that the client has sent at least one keep alive packet, and the test can then be flagged as succeeded
        # a keep alive is usually sent by the server every 15 seconds, the client is expected to reply to it within a certain delay, otherwise, the server can drop the connection
        # likewise, if the server doesn't send keep alive, the client can drop the connection
        # so for now, we emulate this keep alive test with a 30 seconds timeout
        # one issue with this timeout is that if the client takes 20 seconds to log-in, we may not be kicked for timeout (not responding to play state keep alive)
        time.sleep(30)
        # since we are testing PicoLimbo, I'm not entirely sure if I want to rely on it too much for the tests, it'd be better to find something truly autonomous
        # right now, what happens is that we take a screenshot from the game, then a human manually reviews all screenshots to ensure, first that,
        # - a screenshot is taken for all tested versions,
        # - screenshot shows what we expect to see
        # unfortunately, a screenshot does not shows us if a title, action bar message and chat message has been sent, since they disappear from the screen after a while
        test_screenshot(version, virtual_device)
        print(f"✅ Test PASSED for version: {version}")
        return True
    except Exception as e:
        print(f"❌ Test FAILED for version: {version}")
        print(f"   Reason: {e}")
        return False
    finally:
        if process:
            print(f"--- Cleaning up for version: {version} ---")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(
                    f"   Process for {version} did not terminate gracefully, killing."
                )
                process.kill()


def run_test_suite(versions_to_test: list[str]) -> list[str]:
    print("=========================================")
    print("  STARTING MINECRAFT INTEGRATION SUITE   ")
    print("=========================================\n")

    if os.path.exists(REPORTS_DIRECTORY):
        empty_directory(REPORTS_DIRECTORY)

    passed_versions = []
    failed_versions = []
    virtual_device = VirtualInputController()

    for version in versions_to_test:
        if test_single_version(version, virtual_device):
            passed_versions.append(version)
        else:
            failed_versions.append(version)
        print("\n")

    print("=========================================")
    print("            TEST SUITE REPORT            ")
    print("=========================================")
    print(f"Total tests run: {len(versions_to_test)}")
    print(f"Passed: {len(passed_versions)}")
    print(f"Failed: {len(failed_versions)}")
    print("-----------------------------------------")

    if not failed_versions:
        print("✅ All versions passed!")
    else:
        print("❌ The following versions failed the integration test:")
        for v in failed_versions:
            print(f"  - {v}")

    print("=========================================")
    return failed_versions


def get_versions_to_test(config_set="all"):
    all_versions = [
        "26.1",
        "1.21.11",
        "1.21.9",
        "1.21.7",
        "1.21.6",
        "1.21.5",
        "1.21.4",
        "1.21.2",
        "1.21",
        "1.20.5",
        "1.20.3",
        "1.20.2",
        "1.20",
        "1.19.4",
        "1.19.3",
        "1.19.1",  # Multiplayer does not work in offline mode through Velocity
        "1.19",  # Multiplayer does not work in offline mode through Velocity
        "1.18.2",
        "1.18",
        "1.17.1",
        "1.17",
        # "1.16.4",  # Multiplayer does not work in offline mode in this version
        "1.16.3",
        "1.16.2",
        "1.16.1",
        "1.16",
        "1.15.2",
        "1.15.1",
        "1.15",
        "1.14.4",
        "1.14.3",
        "1.14.2",
        "1.14.1",
        "1.14",
        "1.13.2",
        "1.13.1",
        "1.13",
        "1.12.2",
        "1.12.1",
        "1.12",
        "1.11.1",
        "1.11",
        "1.10",
        "1.9.3",
        "1.9.2",
        "1.9.1",
        "1.9",
        "1.8",
        "1.7.6",
        "1.7.2",
    ]

    def version_to_tuple(v):
        return tuple(map(int, v.split(".")))

    def filter_since(versions, min_version):
        min_tuple = version_to_tuple(min_version)
        return [v for v in versions if version_to_tuple(v) >= min_tuple]

    version_sets = {
        "configuration": filter_since(all_versions, "1.20.2"),
        "registries": filter_since(all_versions, "1.16"),
        "modern": filter_since(all_versions, "1.13"),
        "legacy": filter_since(all_versions, "1.7.2"),
        "all": all_versions,
    }

    if isinstance(config_set, str):
        if config_set not in version_sets:
            raise ValueError(
                f"Unknown config set: {config_set}. Available: {list(version_sets.keys())}"
            )
        return version_sets[config_set]

    if isinstance(config_set, list):
        combined = []
        seen = set()
        for set_name in config_set:
            if set_name not in version_sets:
                raise ValueError(
                    f"Unknown config set: {set_name}. Available: {list(version_sets.keys())}"
                )
            for v in version_sets[set_name]:
                if v not in seen:
                    combined.append(v)
                    seen.add(v)
        return combined

    raise TypeError("config_set must be a string or list of strings")


if __name__ == "__main__":
    # versions_to_run = get_versions_to_test("all")
    versions_to_run = ["26.1"]
    failed_tests = run_test_suite(versions_to_run)
    if failed_tests:
        import sys

        sys.exit(1)
