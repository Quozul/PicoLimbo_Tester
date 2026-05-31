"""Virtual input controller for Minecraft automation."""

import subprocess
import time


class VirtualInputController:
    """Controls mouse and keyboard via xdotool, works on any X11/Xvfb display."""

    def __init__(self):
        self.window_id: str | None = None

    def set_window(self, window_id: str):
        self.window_id = window_id

    def _activate(self):
        if self.window_id:
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", self.window_id],
                capture_output=True,
            )
            time.sleep(0.1)

    def move_to(self, x: int, y: int):
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], capture_output=True)

    def click(self):
        subprocess.run(["xdotool", "click", "1"], capture_output=True)

    def close(self):
        pass
