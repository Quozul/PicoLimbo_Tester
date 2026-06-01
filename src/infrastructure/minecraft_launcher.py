"""Minecraft launcher adapter — wraps minecraft_launcher_lib calls.

This module isolates all minecraft_launcher_lib interactions in one place.
If the library API changes, only this file needs updating.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import minecraft_launcher_lib

if TYPE_CHECKING:
    from typing import Protocol

    class MinecraftLauncherProtocol(Protocol):
        """Protocol for MinecraftLauncher used by other modules."""

        def get_command(self, version: str) -> list[str]:
            ...

        def start(self, version: str) -> subprocess.Popen:
            ...


class MinecraftLauncher:
    """Wraps minecraft_launcher_lib to launch Minecraft for integration tests.

    Parameters
    ----------
    game_directory : Path | None
        Directory where minecraft_launcher_lib installs and runs the game.
        Defaults to ``Path("minecraft")``.
    jvm_args : list[str] | None
        JVM arguments passed to the Minecraft process.
        Defaults to ``["-Xmx2G", "-Xms2G"]``.
    resolution : tuple[int, int] | None
        Window resolution as ``(width, height)``.
        Defaults to ``(1024, 768)``.
    """

    def __init__(
        self,
        game_directory: Path | None = None,
        jvm_args: list[str] | None = None,
        resolution: tuple[int, int] | None = None,
    ):
        self._game_directory = game_directory or Path("minecraft")
        self._jvm_args = jvm_args or ["-Xmx2G", "-Xms2G"]
        self._resolution = resolution or (1024, 768)

    # ── Public API ──────────────────────────────────────────────────────────

    def get_command(self, version: str) -> list[str]:
        """Get the Minecraft launch command for a version.

        Parameters
        ----------
        version : str
            Minecraft version string, e.g. ``"1.20.1"``.

        Returns
        -------
        list[str]
            Command list suitable for ``subprocess.Popen``.
        """
        directory = minecraft_launcher_lib.utils.get_minecraft_directory()
        minecraft_launcher_lib.install.install_minecraft_version(version, directory)

        options = minecraft_launcher_lib.utils.generate_test_options()
        options["jvmArguments"] = self._jvm_args
        options["customResolution"] = True
        options["resolutionWidth"] = str(self._resolution[0])
        options["resolutionHeight"] = str(self._resolution[1])
        options["gameDirectory"] = str(self._game_directory)

        return minecraft_launcher_lib.command.get_minecraft_command(
            version, directory, options
        )

    def start(self, version: str) -> subprocess.Popen:
        """Start Minecraft and return the subprocess.Popen handle.

        Parameters
        ----------
        version : str
            Minecraft version string.

        Returns
        -------
        subprocess.Popen
            Running process handle.
        """
        minecraft_command = self.get_command(version)
        directory = minecraft_launcher_lib.utils.get_minecraft_directory()

        return subprocess.Popen(
            minecraft_command,
            cwd=directory,
            stdout=None,
            stderr=None,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
