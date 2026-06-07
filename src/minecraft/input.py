"""Virtual input controller for Minecraft automation."""

import logging
import subprocess
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class VirtualInputController:
    """Controls mouse and keyboard via xdotool, works on any X11/Xvfb display."""

    def __init__(self):
        self.window_id: str | None = None

    def set_window(self, window_id: str):
        self.window_id = window_id
        logger.info("VirtualInputController: set_window=%s", window_id)

    def _activate(self):
        if self.window_id:
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", self.window_id],
                capture_output=True,
            )
            time.sleep(0.1)

    def move_to(self, x: int, y: int):
        logger.info("VirtualInputController: move_to=(%d, %d)", x, y)
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], capture_output=True)

    def click(self, x: int | None = None, y: int | None = None):
        if x is not None and y is not None:
            logger.info("VirtualInputController: moving to (%d, %d)", x, y)
            self.move_to(x, y)
        logger.info("VirtualInputController: clicking (window_id=%s)", self.window_id)
        subprocess.run(["xdotool", "click", "1"], capture_output=True)

    def close(self):
        pass
