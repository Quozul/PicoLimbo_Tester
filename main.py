import os
import pathlib
import re
import shutil
import subprocess
import time
import fcntl

import minecraft_launcher_lib

from virtual_devices import VirtualInputController
from wait_for_quit_button import wait_for_screen_region

GAME_DIRECTORY = str(pathlib.Path().resolve().joinpath("minecraft"))
REPORTS_DIRECTORY = "integration_tests_reports"

# Relative position of the "Quit Game" button within the 854x480 game window.
# Computed from the absolute watch-region coordinates that were calibrated on a
# 2560x1440 Wayland display where the window was centered.
# Newer versions (>= 1.13) have a slightly different menu layout than older ones.
_QUIT_REGION_NEWER = (430, 384, 196, 40)
_QUIT_REGION_OLDER = (430, 384, 196, 40)


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
    relative_x: int,
    relative_y: int,
    window_info: dict,
):
    absolute_x = window_info["x"] + relative_x
    absolute_y = window_info["y"] + relative_y
    print(f"  clicking at screen ({absolute_x}, {absolute_y})")
    mouse.move_to(absolute_x, absolute_y)
    time.sleep(0.1)
    mouse.click()
    time.sleep(0.1)


def wait_for_game(version: str) -> str:
    """Wait for Minecraft to load to the main menu and return the window ID."""
    window_id = None
    deadline = time.time() + 120
    while time.time() < deadline:
        window_id = get_minecraft_window()
        if window_id:
            break
        time.sleep(1)

    if not window_id:
        raise Exception(f"Could not find a window for {version}")

    window_info = get_window_info(window_id)
    if not window_info:
        raise Exception(f"Could not get window geometry for {version}")

    if (
        version.startswith("1.12")
        or version.startswith("1.11")
        or version.startswith("1.10")
        or version.startswith("1.9")
        or version.startswith("1.8")
        or version.startswith("1.7")
    ):
        rel_x, rel_y, rel_w, rel_h = _QUIT_REGION_OLDER
    else:
        rel_x, rel_y, rel_w, rel_h = _QUIT_REGION_NEWER

    watch_region = (
        rel_x,
        rel_y,
        rel_w,
        rel_h,
    )

    matched = wait_for_screen_region(
        reference_images_dir="references",
        region=watch_region,
        timeout=120.0,
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
    click_in_minecraft_window(virtual_device, 426, 283, window_info)
    if version.startswith("1.7."):
        click_in_minecraft_window(virtual_device, 425, 171, window_info)
    else:
        click_in_minecraft_window(virtual_device, 426, 103, window_info)
    click_in_minecraft_window(virtual_device, 217, 391, window_info)


def test_chat_message(process: subprocess.Popen, log_check_timeout: int = 10) -> None:
    start_time = time.time()

    fd = process.stdout.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    log_buffer = ""

    while time.time() - start_time < log_check_timeout:
        if process.poll() is not None:
            print("Minecraft process terminated unexpectedly.")
            break

        try:
            chunk = process.stdout.read()
            if chunk:
                log_buffer += chunk
                while "\n" in log_buffer:
                    line, log_buffer = log_buffer.split("\n", 1)
                    if "Welcome to PicoLimbo!" in line:
                        return
        except (IOError, TypeError):
            pass

        time.sleep(0.1)

    raise Exception("Integration test FAILED: welcome message not received.")


def start_minecraft(version: str) -> subprocess.Popen:
    minecraft_directory = minecraft_launcher_lib.utils.get_minecraft_directory()
    minecraft_launcher_lib.install.install_minecraft_version(
        version, minecraft_directory
    )

    options = minecraft_launcher_lib.utils.generate_test_options()
    options["jvmArguments"] = ["-Xmx2G", "-Xms2G"]
    options["customResolution"] = True
    options["resolutionWidth"] = "854"
    options["resolutionHeight"] = "480"
    options["gameDirectory"] = GAME_DIRECTORY
    minecraft_command = minecraft_launcher_lib.command.get_minecraft_command(
        version, minecraft_directory, options
    )

    return subprocess.Popen(
        minecraft_command,
        cwd=minecraft_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
        test_chat_message(process, log_check_timeout=15)
        time.sleep(2)
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
    versions_to_run = ["1.9"]
    failed_tests = run_test_suite(versions_to_run)
    if failed_tests:
        import sys

        sys.exit(1)
