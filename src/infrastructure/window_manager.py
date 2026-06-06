"""Window manager adapter — wraps xdotool window management calls.

This module isolates all xdotool interactions in one place.
If the xdotool API changes, only this file needs updating.
"""

from __future__ import annotations

import re
import subprocess


class WindowManager:
    """Wraps xdotool to manage Minecraft windows for integration tests.

    All methods return ``None`` on failure rather than raising exceptions,
    so callers can handle missing windows gracefully.
    """

    def search_by_name(self, pattern: str) -> str | None:
        """Search for a window by name pattern.

        Returns the first matching window ID, or ``None`` if no match.
        """
        result = subprocess.run(
            ["xdotool", "search", "--name", pattern],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
        return None

    def search_by_class(self, class_name: str) -> str | None:
        """Search for a window by class.

        Returns the last matching window ID, or ``None`` if no match.
        """
        result = subprocess.run(
            ["xdotool", "search", "--class", class_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[-1]
        return None

    def get_geometry(self, window_id: str) -> dict[str, int] | None:
        """Get window geometry.

        Returns ``{"x": int, "y": int, "width": int, "height": int}``
        or ``None`` if the geometry could not be parsed.
        """
        result = subprocess.run(
            ["xdotool", "getwindowgeometry", window_id],
            capture_output=True,
            text=True,
        )
        return parse_window_info(result.stdout.strip())

    def move_to(self, window_id: str, x: int, y: int) -> None:
        """Move a window to absolute coordinates."""
        subprocess.run(
            ["xdotool", "windowmove", window_id, str(x), str(y)],
            capture_output=True,
        )


def parse_window_info(window_text: str) -> dict[str, int] | None:
    """Parse xdotool getwindowgeometry output into a dict.

    Parameters
    ----------
    window_text : str
        Raw output from ``xdotool getwindowgeometry``, e.g.::

            width=1024  height=768
            depth=24
            x=0     y=0

    Returns
    -------
    dict[str, int] | None
        ``{"x": 0, "y": 0, "width": 1024, "height": 768}`` or ``None``
        if the text doesn't contain the expected fields.
    """
    x_match = re.search(r"x\s*[=:]\s*(-?\d+)", window_text, re.IGNORECASE)
    y_match = re.search(r"y\s*[=:]\s*(-?\d+)", window_text, re.IGNORECASE)
    width_match = re.search(r"width\s*[=:]\s*(\d+)", window_text, re.IGNORECASE)
    height_match = re.search(r"height\s*[=:]\s*(\d+)", window_text, re.IGNORECASE)

    if not (x_match and y_match and width_match and height_match):
        return None

    return {
        "x": int(x_match.group(1)),
        "y": int(y_match.group(1)),
        "width": int(width_match.group(1)),
        "height": int(height_match.group(1)),
    }
