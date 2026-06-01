"""Unit tests for src/infrastructure/minecraft_launcher.py."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.minecraft_launcher import MinecraftLauncher


class TestMinecraftLauncherInit:
    """Tests for MinecraftLauncher.__init__."""

    def test_defaults(self):
        launcher = MinecraftLauncher()
        assert launcher._game_directory == Path("minecraft")
        assert launcher._jvm_args == ["-Xmx2G", "-Xms2G"]
        assert launcher._resolution == (1024, 768)

    def test_custom_game_directory(self):
        launcher = MinecraftLauncher(game_directory=Path("/custom/mc"))
        assert launcher._game_directory == Path("/custom/mc")

    def test_custom_jvm_args(self):
        launcher = MinecraftLauncher(jvm_args=["-Xmx4G", "-Xms4G"])
        assert launcher._jvm_args == ["-Xmx4G", "-Xms4G"]

    def test_custom_resolution(self):
        launcher = MinecraftLauncher(resolution=(1920, 1080))
        assert launcher._resolution == (1920, 1080)

    def test_all_custom(self):
        launcher = MinecraftLauncher(
            game_directory=Path("/app/minecraft"),
            jvm_args=["-Xmx4G", "-Xms4G"],
            resolution=(1920, 1080),
        )
        assert launcher._game_directory == Path("/app/minecraft")
        assert launcher._jvm_args == ["-Xmx4G", "-Xms4G"]
        assert launcher._resolution == (1920, 1080)


class TestGetCommand:
    """Tests for MinecraftLauncher.get_command."""

    def test_returns_list_of_strings(self):
        launcher = MinecraftLauncher()
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory") as dir_mock, \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options") as opts_mock, \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            dir_mock.return_value = Path("/mc")
            opts_mock.return_value = {}
            cmd_mock.return_value = ["java", "-version"]
            result = launcher.get_command("1.20.1")
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_includes_jvm_args(self):
        launcher = MinecraftLauncher(jvm_args=["-Xmx4G", "-Xms4G"])
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory"), \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options") as opts_mock, \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            opts_mock.return_value = {}
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.20.1")
            opts_mock.return_value["jvmArguments"] == ["-Xmx4G", "-Xms4G"]
            # Verify the options dict passed to get_minecraft_command has the JVM args
            call_kwargs = cmd_mock.call_args
            options = call_kwargs[0][2]  # third positional arg
            assert options["jvmArguments"] == ["-Xmx4G", "-Xms4G"]

    def test_includes_custom_resolution(self):
        launcher = MinecraftLauncher(resolution=(1920, 1080))
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory"), \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options") as opts_mock, \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            opts_mock.return_value = {}
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.20.1")
            call_kwargs = cmd_mock.call_args
            options = call_kwargs[0][2]
            assert options["customResolution"] is True
            assert options["resolutionWidth"] == "1920"
            assert options["resolutionHeight"] == "1080"

    def test_includes_game_directory(self):
        launcher = MinecraftLauncher(game_directory=Path("/custom/mc"))
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory"), \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options") as opts_mock, \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            opts_mock.return_value = {}
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.20.1")
            call_kwargs = cmd_mock.call_args
            options = call_kwargs[0][2]
            assert options["gameDirectory"] == "/custom/mc"

    def test_default_resolution(self):
        launcher = MinecraftLauncher()
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory"), \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options") as opts_mock, \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            opts_mock.return_value = {}
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.20.1")
            call_kwargs = cmd_mock.call_args
            options = call_kwargs[0][2]
            assert options["resolutionWidth"] == "1024"
            assert options["resolutionHeight"] == "768"

    def test_default_jvm_args(self):
        launcher = MinecraftLauncher()
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory"), \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options") as opts_mock, \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            opts_mock.return_value = {}
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.20.1")
            call_kwargs = cmd_mock.call_args
            options = call_kwargs[0][2]
            assert options["jvmArguments"] == ["-Xmx2G", "-Xms2G"]

    def test_calls_install_minecraft_version(self):
        """Ensure install_minecraft_version is called with the correct version."""
        launcher = MinecraftLauncher()
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory") as dir_mock, \
             patch("minecraft_launcher_lib.install.install_minecraft_version") as install_mock, \
             patch("minecraft_launcher_lib.utils.generate_test_options"), \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            dir_mock.return_value = Path("/mc")
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.19.4")
            install_mock.assert_called_once_with("1.19.4", Path("/mc"))

    def test_version_1_7_10(self):
        launcher = MinecraftLauncher()
        with patch("minecraft_launcher_lib.utils.get_minecraft_directory"), \
             patch("minecraft_launcher_lib.install.install_minecraft_version"), \
             patch("minecraft_launcher_lib.utils.generate_test_options"), \
             patch("minecraft_launcher_lib.command.get_minecraft_command") as cmd_mock:
            cmd_mock.return_value = ["java", "-version"]
            launcher.get_command("1.7.10")
            cmd_mock.assert_called_once()


class TestStart:
    """Tests for MinecraftLauncher.start."""

    def test_returns_subprocess_popen(self):
        launcher = MinecraftLauncher()
        with patch.object(
            launcher, "get_command", return_value=["java", "-version"]
        ) as get_cmd_mock, \
             patch("minecraft_launcher_lib.utils.get_minecraft_directory") as dir_mock, \
             patch("subprocess.Popen") as popen_mock:
            dir_mock.return_value = Path("/mc")
            result = launcher.start("1.20.1")
            get_cmd_mock.assert_called_once_with("1.20.1")
            popen_mock.assert_called_once()
            assert result is popen_mock.return_value
            # Verify cwd is the minecraft directory
            assert popen_mock.call_args[1]["cwd"] == Path("/mc")

    def test_passes_correct_kwargs_to_popen(self):
        launcher = MinecraftLauncher()
        with patch.object(
            launcher, "get_command", return_value=["java", "-version"]
        ), \
             patch("minecraft_launcher_lib.utils.get_minecraft_directory") as dir_mock, \
             patch("subprocess.Popen") as popen_mock:
            dir_mock.return_value = Path("/mc")
            launcher.start("1.20.1")
            kwargs = popen_mock.call_args[1]
            assert kwargs["stdout"] is None
            assert kwargs["stderr"] is None
            assert kwargs["text"] is True
            assert kwargs["encoding"] == "utf-8"
            assert kwargs["errors"] == "ignore"

    def test_default_minecraft_directory(self):
        """When no game_directory is set, get_minecraft_directory() is used for cwd."""
        launcher = MinecraftLauncher()
        with patch.object(
            launcher, "get_command", return_value=["java", "-version"]
        ), \
             patch("minecraft_launcher_lib.utils.get_minecraft_directory") as dir_mock, \
             patch("subprocess.Popen") as popen_mock:
            dir_mock.return_value = Path("/mc")
            launcher.start("1.20.1")
            assert popen_mock.call_args[1]["cwd"] == Path("/mc")
