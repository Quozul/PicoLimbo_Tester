import pathlib
import shutil
import subprocess
import time
import minecraft_launcher_lib
import re
import os
import fcntl

from virtual_devices import VirtualInputController
from wait_for_quit_button import wait_for_screen_region

GAME_DIRECTORY = str(pathlib.Path().resolve().joinpath("minecraft"))
REPORTS_DIRECTORY = "integration_tests_reports"


def parse_window_info(window_text):
    position_pattern = r"Position:\s*(\d+),(\d+)"
    geometry_pattern = r"Geometry:\s*(\d+)x(\d+)"

    position_match = re.search(position_pattern, window_text)
    geometry_match = re.search(geometry_pattern, window_text)

    if position_match and geometry_match:
        x = int(position_match.group(1))
        y = int(position_match.group(2))
        width = int(geometry_match.group(1))
        height = int(geometry_match.group(2))

        x_offset = 61
        y_offset = 92

        return {"x": x + x_offset, "y": y + y_offset, "width": width, "height": height}
    else:
        return None


def get_minecraft_window():
    try:
        window_titles = ["Minecraft*", "Minecraft", "Minecraft 1.13"]

        for title in window_titles:
            result = subprocess.run(
                ["xdotool", "search", "--name", title], capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split("\n")[0]
                return window_id

        result = subprocess.run(
            ["xdotool", "search", "--class", "java"], capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            window_ids = result.stdout.strip().split("\n")
            return window_ids[-1]

        return None
    except Exception as e:
        print(f"Error finding Minecraft window: {e}")
        return None


def get_window_info(window_id):
    result = subprocess.run(
        ["xdotool", "getwindowgeometry", window_id], capture_output=True, text=True
    )
    return parse_window_info(result.stdout.strip())


def click_in_minecraft_window(
    mouse: VirtualInputController, relative_x: int, relative_y: int, window_info
):
    if window_info:
        absolute_x = window_info["x"] + relative_x
        absolute_y = window_info["y"] + relative_y

        mouse.move_to(absolute_x, absolute_y)
        time.sleep(0.1)
        mouse.click()
        time.sleep(0.1)


def wait_for_game(version: str) -> bool:
    if (
        version.startswith("1.12")
        or version.startswith("1.11")
        or version.startswith("1.10")
        or version.startswith("1.9")
        or version.startswith("1.8")
        or version.startswith("1.7")
    ):
        watch_region = (1283, 901, 196, 40)
    else:
        watch_region = (1283, 864, 196, 40)

    matched = wait_for_screen_region(
        reference_images_dir="references",
        region=watch_region,
        timeout=60.0,
        interval=0.5,
    )
    if not matched:
        raise Exception(f"Could not find a match for {version}")
    return True


def log_to_multiplayer(version: str, virtual_device: VirtualInputController) -> bool:
    window_id = None
    for attempt in range(10):
        window_id = get_minecraft_window()
        if window_id:
            break
        time.sleep(1)

    if not window_id:
        raise Exception(f"Could not find a window for {version}")

    window_info = get_window_info(window_id)
    print("window info=", window_info)

    # 37 is window decoration
    click_in_minecraft_window(virtual_device, 426, 283 - 37, window_info)
    if version.startswith("1.7."):
        click_in_minecraft_window(virtual_device, 425, 171 - 37, window_info)
    else:
        click_in_minecraft_window(virtual_device, 426, 103 - 37, window_info)
    click_in_minecraft_window(virtual_device, 217, 391 - 37, window_info)
    return True


def test_chat_message(process: subprocess.Popen[str], log_check_timeout=10) -> bool:
    found_message = False
    start_time = time.time()

    fd = process.stdout.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    log_buffer = ""

    try:
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
                            found_message = True
                            break
            except (IOError, TypeError):
                pass

            if found_message:
                break

            time.sleep(0.1)

    finally:
        if found_message:
            return True
        else:
            raise Exception("Integration test FAILED.")


def start_minecraft(version: str) -> subprocess.Popen[str]:
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
    """Empty the contents of the given directory."""
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
    """Get the latest screenshot file from the given directory."""
    files = [
        f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))
    ]
    if not files:
        raise FileNotFoundError("No screenshots found in the directory.")
    latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
    return os.path.join(directory, latest_file)


def test_screenshot(version: str, virtual_device: VirtualInputController) -> bool:
    screenshot_directory = os.path.join(GAME_DIRECTORY, "screenshots")

    # Empty the directory first if not empty
    empty_directory(screenshot_directory)

    # Take a screenshot by pressing F2
    virtual_device.press_f3()
    time.sleep(0.5)
    virtual_device.press_f2()
    time.sleep(0.5)

    # Move the latest screenshot to the test reports directory
    if not os.path.exists(REPORTS_DIRECTORY):
        os.makedirs(REPORTS_DIRECTORY)

    try:
        latest_screenshot = get_latest_screenshot(screenshot_directory)
        basename = os.path.basename(latest_screenshot)
        shutil.move(
            latest_screenshot,
            os.path.join(REPORTS_DIRECTORY, f"{version}_{basename}"),
        )
    except FileNotFoundError as e:
        raise e

    return True


def test_single_version(version: str, virtual_device: VirtualInputController) -> bool:
    print(f"--- Starting test for version: {version} ---")
    process = None

    try:
        process = start_minecraft(version)
        wait_for_game(version)
        log_to_multiplayer(version, virtual_device)

        # Wait for the welcome message from the server to confirm a successful login.
        test_chat_message(process, log_check_timeout=15)

        # Wait a moment for the world to render before taking a screenshot.
        time.sleep(2)

        # Take a screenshot to verify the game state visually.
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


def run_test_suite(versions_to_test: list[str]):
    print("=========================================")
    print("  STARTING MINECRAFT INTEGRATION SUITE   ")
    print("=========================================\n")

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

    # --- Final Report ---
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
        for version in failed_versions:
            print(f"  - {version}")

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
        # "1.16.4", # Multiplayer does not work in offline mode in this version
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

    def version_to_tuple(version):
        """Convert version string to tuple for comparison"""
        return tuple(map(int, version.split(".")))

    def filter_since_version(versions, min_version):
        """Filter versions that are >= min_version"""
        min_tuple = version_to_tuple(min_version)
        return [v for v in versions if version_to_tuple(v) >= min_tuple]

    version_sets = {
        "configuration": filter_since_version(all_versions, "1.20.2"),
        "registries": filter_since_version(all_versions, "1.16"),
        "modern": filter_since_version(all_versions, "1.13"),
        "legacy": filter_since_version(all_versions, "1.7.2"),
        "all": all_versions,
    }

    if isinstance(config_set, str):
        if config_set not in version_sets:
            raise ValueError(
                f"Unknown config set: {config_set}. Available: {list(version_sets.keys())}"
            )
        return version_sets[config_set]

    elif isinstance(config_set, list):
        # Combine multiple sets and remove duplicates while preserving order
        combined = []
        seen = set()
        for set_name in config_set:
            if set_name not in version_sets:
                raise ValueError(
                    f"Unknown config set: {set_name}. Available: {list(version_sets.keys())}"
                )
            for version in version_sets[set_name]:
                if version not in seen:
                    combined.append(version)
                    seen.add(version)
        return combined
    else:
        raise TypeError("config_set must be a string or list of strings")


if __name__ == "__main__":
    versions_to_run = get_versions_to_test("all")

    failed_tests = run_test_suite(versions_to_run)

    # This is useful for CI/CD pipelines
    if failed_tests:
        # Exit with a non-zero status code to indicate failure
        import sys

        sys.exit(1)
