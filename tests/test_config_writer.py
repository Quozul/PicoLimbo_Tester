"""Tests for the ConfigWriter ACL adapter."""

import textwrap
from pathlib import Path

import pytest

from src.infrastructure.config_writer import (
    ConfigWriter,
    ServerEntry,
    _manual_toml_dump,
    _toml_value,
)
from src.versions import Version


# ---------------------------------------------------------------------------
# ServerEntry
# ---------------------------------------------------------------------------

class TestServerEntry:
    def test_from_tuple(self):
        entry = ServerEntry.from_tuple(("mc.example.com:25565", "Test", True))
        assert entry.ip == "mc.example.com:25565"
        assert entry.name == "Test"
        assert entry.hidden is True

    def test_from_dict(self):
        entry = ServerEntry.from_dict({"ip": "127.0.0.1:25565", "name": "Local", "hidden": False})
        assert entry.ip == "127.0.0.1:25565"
        assert entry.name == "Local"
        assert entry.hidden is False

    def test_from_dict_defaults(self):
        entry = ServerEntry.from_dict({"ip": "127.0.0.1:25565"})
        assert entry.name == "Minecraft Server"
        assert entry.hidden is False

    def test_init_defaults(self):
        entry = ServerEntry("127.0.0.1:25565")
        assert entry.ip == "127.0.0.1:25565"
        assert entry.name == "Minecraft Server"
        assert entry.hidden is False


# ---------------------------------------------------------------------------
# _toml_value / _manual_toml_dump
# ---------------------------------------------------------------------------

class TestTOMLHelpers:
    def test_toml_value_bool_true(self):
        assert _toml_value(True) == "true"

    def test_toml_value_bool_false(self):
        assert _toml_value(False) == "false"

    def test_toml_value_string(self):
        assert _toml_value("hello") == '"hello"'

    def test_toml_value_string_with_quotes(self):
        assert _toml_value('he said "hi"') == '"he said \\"hi\\""'

    def test_toml_value_list(self):
        assert _toml_value(["a", "b"]) == '["a", "b"]'

    def test_toml_value_int(self):
        assert _toml_value(42) == "42"

    def test_manual_dump_simple(self):
        result = _manual_toml_dump({"key": "value"})
        assert result == 'key = "value"'

    def test_manual_dump_nested(self):
        result = _manual_toml_dump({"outer": {"inner": "val"}})
        expected = textwrap.dedent("""\
            [outer]
              inner = "val"
        """).strip()
        assert result == expected

    def test_manual_dump_mixed(self):
        result = _manual_toml_dump({
            "bind": "0.0.0.0:25565",
            "online-mode": False,
            "servers": {"limbo": "127.0.0.1:25565"},
        })
        assert "bind = \"0.0.0.0:25565\"" in result
        assert "online-mode = false" in result
        assert "[servers]" in result


# ---------------------------------------------------------------------------
# write_servers_dat
# ---------------------------------------------------------------------------

class TestWriteServersDat:
    def test_creates_file(self, tmp_path):
        writer = ConfigWriter()
        servers = [ServerEntry("127.0.0.1:25565", "Test Server", False)]
        out = tmp_path / "servers.dat"
        writer.write_servers_dat(out, servers)
        assert out.exists()

    def test_creates_parent_directories(self, tmp_path):
        writer = ConfigWriter()
        servers = [ServerEntry("127.0.0.1:25565")]
        out = tmp_path / "sub" / "dir" / "servers.dat"
        writer.write_servers_dat(out, servers)
        assert out.exists()

    def test_single_server_entry(self, tmp_path):
        """Write and re-read the NBT file to verify structure."""
        from nbtlib import File as NbtFile
        writer = ConfigWriter()
        servers = [ServerEntry("mc.example.com:25565", "My Server", True)]
        out = tmp_path / "servers.dat"
        writer.write_servers_dat(out, servers)

        # Re-read and verify (servers.dat is not gzipped)
        nbt = NbtFile.load(out, gzipped=False)
        servers_list = nbt["servers"]
        assert len(servers_list) == 1
        entry = servers_list[0]
        assert entry["ip"] == "mc.example.com:25565"
        assert entry["name"] == "My Server"
        assert entry["hidden"] == 1

    def test_hidden_false(self, tmp_path):
        from nbtlib import File as NbtFile
        writer = ConfigWriter()
        servers = [ServerEntry("localhost:25565", "Local", False)]
        out = tmp_path / "servers.dat"
        writer.write_servers_dat(out, servers)

        nbt = NbtFile.load(out, gzipped=False)
        entry = nbt["servers"][0]
        assert entry["hidden"] == 0

    def test_multiple_servers(self, tmp_path):
        from nbtlib import File as NbtFile
        writer = ConfigWriter()
        servers = [
            ServerEntry("server1.example.com", "Server 1", False),
            ServerEntry("server2.example.com", "Server 2", True),
        ]
        out = tmp_path / "servers.dat"
        writer.write_servers_dat(out, servers)

        nbt = NbtFile.load(out, gzipped=False)
        assert len(nbt["servers"]) == 2
        assert nbt["servers"][0]["ip"] == "server1.example.com"
        assert nbt["servers"][1]["ip"] == "server2.example.com"
        assert nbt["servers"][1]["hidden"] == 1

    def test_empty_servers_list(self, tmp_path):
        """An empty servers list should produce a valid file."""
        from nbtlib import File as NbtFile
        writer = ConfigWriter()
        out = tmp_path / "servers.dat"
        writer.write_servers_dat(out, [])

        nbt = NbtFile.load(out, gzipped=False)
        assert len(nbt["servers"]) == 0


# ---------------------------------------------------------------------------
# write_options_txt
# ---------------------------------------------------------------------------

class TestWriteOptionsTxt:
    def test_creates_file(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 5, 754))
        assert out.exists()

    def test_creates_parent_directories(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "sub" / "dir" / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 5, 754))
        assert out.exists()

    def test_1_7_10_empty(self, tmp_path):
        """1.7.10 — before 1.12, before 1.15.2, before 1.16.4."""
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 7, 10, 5))
        assert out.read_text() == ""

    def test_1_11_0_empty(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 11, 0, 315))
        assert out.read_text() == ""

    def test_1_12_0_tutorial_step_only(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 12, 0, 335))
        assert out.read_text() == "tutorialStep:none"

    def test_1_12_2_tutorial_step_only(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 12, 2, 340))
        assert out.read_text() == "tutorialStep:none"

    def test_1_15_2_skip_and_tutorial(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 15, 2, 578))
        assert out.read_text() == "skipMultiplayerWarning:true\ntutorialStep:none"

    def test_1_15_1_tutorial_only(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 15, 1, 575))
        assert out.read_text() == "tutorialStep:none"

    def test_1_16_3_skip_and_tutorial(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 3, 753))
        assert out.read_text() == "skipMultiplayerWarning:true\ntutorialStep:none"

    def test_1_16_4_all_three(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 4, 754))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    def test_1_16_5_all_three(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 5, 754))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    def test_1_17_all_three(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 17, 0, 755))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    def test_26_1_2_all_three(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(26, 1, 2, 775))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    def test_no_trailing_newline(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 5, 754))
        content = out.read_bytes()
        assert not content.endswith(b"\n")

    def test_no_extra_whitespace(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 16, 5, 754))
        lines = out.read_text().split("\n")
        assert lines == [
            "skipMultiplayerWarning:true",
            "tutorialStep:none",
            "joinedFirstServer:true",
        ]

    def test_single_option_no_newline(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 12, 0, 335))
        assert out.read_text() == "tutorialStep:none"
        assert "\n" not in out.read_text()

    def test_empty_file_when_no_options_supported(self, tmp_path):
        writer = ConfigWriter()
        out = tmp_path / "options.txt"
        writer.write_options_txt(out, Version(1, 7, 10, 5))
        assert out.exists()
        assert out.stat().st_size == 0


# ---------------------------------------------------------------------------
# write_velocity_toml
# ---------------------------------------------------------------------------

class TestWriteVelocityToml:
    def test_creates_file(self, tmp_path):
        writer = ConfigWriter()
        config_dict = {"bind": "0.0.0.0:25565"}
        out = tmp_path / "velocity.toml"
        writer.write_velocity_toml(out, config_dict)
        assert out.exists()

    def test_creates_parent_directories(self, tmp_path):
        writer = ConfigWriter()
        config_dict = {"bind": "0.0.0.0:25565"}
        out = tmp_path / "sub" / "dir" / "velocity.toml"
        writer.write_velocity_toml(out, config_dict)
        assert out.exists()

    def test_content_with_tomli_w_available(self, tmp_path):
        """If tomli-w is available, verify the output is valid TOML."""
        try:
            import tomli_w  # noqa: F401
            has_tomli_w = True
        except ImportError:
            has_tomli_w = False

        if not has_tomli_w:
            pytest.skip("tomli-w not installed")

        writer = ConfigWriter()
        config_dict = {
            "bind": "0.0.0.0:25565",
            "online-mode": False,
            "player-info-forwarding-mode": "MODERN",
            "forwarding-secret-file": "forwarding.secret",
            "servers": {
                "limbo": "127.0.0.1:30066",
                "try": ["limbo"],
            },
            "forced-hosts": {},
        }
        out = tmp_path / "velocity.toml"
        writer.write_velocity_toml(out, config_dict)

        # Verify we can parse it back with tomli
        import tomli
        content = tomli.loads(out.read_text())
        assert content["bind"] == "0.0.0.0:25565"
        assert content["online-mode"] is False
        assert content["player-info-forwarding-mode"] == "MODERN"
        assert content["forwarding-secret-file"] == "forwarding.secret"
        assert content["servers"]["limbo"] == "127.0.0.1:30066"
        assert content["servers"]["try"] == ["limbo"]

    def test_content_without_tomli_w(self, tmp_path):
        """Verify fallback manual serialization produces valid TOML."""
        import sys
        # Patch sys.modules to simulate missing tomli-w
        saved = sys.modules.pop("tomli_w", None)

        try:
            writer = ConfigWriter()
            config_dict = {
                "bind": "0.0.0.0:25565",
                "online-mode": False,
                "servers": {"limbo": "127.0.0.1:30066"},
            }
            out = tmp_path / "velocity.toml"
            writer.write_velocity_toml(out, config_dict)

            content = out.read_text()
            assert 'bind = "0.0.0.0:25565"' in content
            assert "online-mode = false" in content
            assert "[servers]" in content
            assert 'limbo = "127.0.0.1:30066"' in content
        finally:
            if saved is not None:
                sys.modules["tomli_w"] = saved
