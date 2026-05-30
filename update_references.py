import os
import time
import subprocess
import pyscreenshot as ImageGrab
from minecraft_integration_tests import (
    start_minecraft,
    get_minecraft_window,
    get_window_info,
)

VERSIONS = ["1.7.2", "1.13.2", "1.19.3", "1.19.4", "1.21.8"]
SCREENSHOTS_DIR = "full_screenshots"
START_TIMEOUT = 15


def wait_for_window(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        wid = get_minecraft_window()
        if wid:
            info = get_window_info(wid)
            if info:
                return wid, info
        time.sleep(1)
    return None, None


def update_version_reference(version):
    print(f"Updating reference for version: {version}")
    print("DEBUG: Starting update_version_reference")
    process = None
    try:
        process = start_minecraft(version)
        print("DEBUG: Minecraft started, waiting for window...")
        window_id, window_info = wait_for_window()

        if not window_id or not window_info:
            print("DEBUG: Window not found")
            raise Exception(f"Could not find a stable window for {version}")

        print(f"DEBUG: Window found: {window_id}, info: {window_info}")

        # Give it a bit more time to settle and the main menu to actually appear
        print(f"DEBUG: Sleeping for {START_TIMEOUT} seconds...")
        time.sleep(START_TIMEOUT)

        print(f"Capturing full screen for {version}...")
        img = ImageGrab.grab().convert("RGB")

        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        img.save(os.path.join(SCREENSHOTS_DIR, f"{version}.png"))
        print(f"Saved screenshot for {version}")

    except Exception as e:
        print(f"Error updating {version}: {e}")
    finally:
        if process:
            print(f"Cleaning up {version}...")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    for v in VERSIONS:
        update_version_reference(v)
