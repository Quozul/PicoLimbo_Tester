import os
from unittest.mock import patch, MagicMock

import pytest

from src.minecraft.env import create_options_txt, create_servers_dat
from src.versions import Version


# ---------------------------------------------------------------------------
# create_options_txt
# ---------------------------------------------------------------------------

class TestCreateOptionsTxt:
    """Test that options.txt is written with the correct key=value pairs
    for each Minecraft version."""

    # -- 1.7.10 / 1.11.0 (before 1.12, before 1.15.2) ---------------------
    # Both skipMultiplayerWarning (1.15.2+), tutorialStep (1.12+), and
    # joinedFirstServer (1.16.4+) are unsupported, so the file should be
    # empty.

    def test_1_7_10_empty_options(self, tmp_path):
        v = Version(1, 7, 10, 5)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == ""

    def test_1_11_0_empty_options(self, tmp_path):
        v = Version(1, 11, 0, 315)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == ""

    # -- 1.12.0 (1.12+, before 1.15.2) ------------------------------------
    # tutorialStep is supported; skipMultiplayerWarning and joinedFirstServer
    # are not.

    def test_1_12_0_tutorial_step_only(self, tmp_path):
        v = Version(1, 12, 0, 335)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == "tutorialStep:none"

    # -- 1.12.2 (1.12+, before 1.15.2) ------------------------------------

    def test_1_12_2_tutorial_step_only(self, tmp_path):
        v = Version(1, 12, 2, 340)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == "tutorialStep:none"

    # -- 1.15.2 (skipMultiplayerWarning introduced) ------------------------

    def test_1_15_2_skip_multiplayer_and_tutorial(self, tmp_path):
        v = Version(1, 15, 2, 578)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == "skipMultiplayerWarning:true\ntutorialStep:none"

    # -- 1.15.1 (before skipMultiplayerWarning) ----------------------------

    def test_1_15_1_tutorial_step_only(self, tmp_path):
        v = Version(1, 15, 1, 575)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == "tutorialStep:none"

    # -- 1.16.3 (1.16.3, before joinedFirstServer) -------------------------

    def test_1_16_3_skip_and_tutorial(self, tmp_path):
        v = Version(1, 16, 3, 753)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == "skipMultiplayerWarning:true\ntutorialStep:none"

    # -- 1.16.4 (joinedFirstServer introduced) -----------------------------

    def test_1_16_4_all_three_options(self, tmp_path):
        v = Version(1, 16, 4, 754)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    # -- 1.16.5 (all three options) ----------------------------------------

    def test_1_16_5_all_three_options(self, tmp_path):
        v = Version(1, 16, 5, 754)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    # -- 1.17+ (all three options) -----------------------------------------

    def test_1_17_all_three_options(self, tmp_path):
        v = Version(1, 17, 0, 755)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    # -- 26.1.2 (all three options) ----------------------------------------

    def test_26_1_2_all_three_options(self, tmp_path):
        v = Version(26, 1, 2, 775)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == (
            "skipMultiplayerWarning:true\n"
            "tutorialStep:none\n"
            "joinedFirstServer:true"
        )

    # -- No trailing newline ------------------------------------------------

    def test_no_trailing_newline(self, tmp_path):
        v = Version(1, 16, 5, 754)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        content = out.read_bytes()
        assert not content.endswith(b"\n")

    # -- Parent directory creation ------------------------------------------

    def test_creates_parent_directories(self, tmp_path):
        v = Version(1, 16, 5, 754)
        out = tmp_path / "sub" / "dir" / "options.txt"
        create_options_txt(v, str(out))
        assert out.exists()

    # -- Output file content is exactly the options, nothing extra ----------

    def test_no_extra_whitespace(self, tmp_path):
        v = Version(1, 16, 5, 754)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        lines = out.read_text().split("\n")
        assert lines == [
            "skipMultiplayerWarning:true",
            "tutorialStep:none",
            "joinedFirstServer:true",
        ]

    # -- Single option has no newline separator -----------------------------

    def test_single_option_no_newline(self, tmp_path):
        v = Version(1, 12, 0, 335)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.read_text() == "tutorialStep:none"
        assert "\n" not in out.read_text()

    # -- Empty options file (no supported options) --------------------------

    def test_empty_file_when_no_options_supported(self, tmp_path):
        v = Version(1, 7, 10, 5)
        out = tmp_path / "options.txt"
        create_options_txt(v, str(out))
        assert out.exists()
        assert out.stat().st_size == 0


# ---------------------------------------------------------------------------
# create_servers_dat
# ---------------------------------------------------------------------------

class TestCreateServersDat:
    """Test that servers.dat is written and parent directories are created.

    We mock the nbtlib imports (File, List, Compound, String, Byte) to avoid
    needing the actual NBT library installed.
    """

    @pytest.fixture
    def mock_nbt(self):
        """Mock all nbtlib symbols imported into src.minecraft.env.

        The mocks must behave like the real nbtlib types so the function's
        dict/list construction works and we can inspect the resulting
        structure.
        """
        mock_file = MagicMock()
        mock_file.return_value = MagicMock()

        # Compound({...}) should return the dict it receives
        def compound_factory(d):
            return dict(d)

        # NbtList[Compound]([...]) — NbtList must be subscriptable (generic).
        # NbtList[T] returns a callable that accepts an iterable and returns
        # a plain list.
        class MockNbtList:
            def __class_getitem__(cls, item):
                return _NbtListCallable

        class _NbtListCallable:
            """Callable class returned by NbtList[T]."""
            def __new__(cls, lst=None):
                return list(lst) if lst is not None else []

        # String("value") and Byte(1) should return the value itself
        def string_factory(s):
            return s

        def byte_factory(b):
            return int(b)

        with patch.multiple(
            "src.minecraft.env",
            File=mock_file,
            NbtList=MockNbtList,
            Compound=compound_factory,
            String=string_factory,
            Byte=byte_factory,
        ):
            yield {
                "File": mock_file,
            }

    def test_creates_file(self, mock_nbt, tmp_path):
        """Verify File() is called and save() is invoked with the output path."""
        out = tmp_path / "servers.dat"
        create_servers_dat(str(out), "127.0.0.1:25565", "Test Server", False)
        mock_nbt["File"].return_value.save.assert_called_once_with(str(out))

    def test_creates_parent_directories(self, mock_nbt, tmp_path):
        """Verify the parent directory is created on disk (makedirs is not mocked)."""
        out = tmp_path / "sub" / "servers.dat"
        create_servers_dat(str(out), "127.0.0.1:25565", "Test Server", False)
        # Parent directory should exist; the file itself is not written because
        # File.save() is mocked.
        assert (tmp_path / "sub").exists()

    def test_calls_file_with_correct_structure(self, mock_nbt, tmp_path):
        out = tmp_path / "servers.dat"
        create_servers_dat(str(out), "mc.example.com:25565", "My Server", True)

        # File() should have been called with a Compound (dict) containing a
        # "servers" list with one entry.
        call_args = mock_nbt["File"].call_args
        root_compound = call_args[0][0]

        assert "servers" in root_compound
        servers_list = root_compound["servers"]
        assert len(servers_list) == 1

        entry = servers_list[0]
        assert entry["ip"] == "mc.example.com:25565"
        assert entry["name"] == "My Server"
        assert entry["hidden"] == 1

    def test_hidden_false(self, mock_nbt, tmp_path):
        out = tmp_path / "servers.dat"
        create_servers_dat(str(out), "localhost:25565", "Local", False)

        root_compound = mock_nbt["File"].call_args[0][0]
        entry = root_compound["servers"][0]
        assert entry["hidden"] == 0

    def test_hidden_true(self, mock_nbt, tmp_path):
        out = tmp_path / "servers.dat"
        create_servers_dat(str(out), "localhost:25565", "Local", True)

        root_compound = mock_nbt["File"].call_args[0][0]
        entry = root_compound["servers"][0]
        assert entry["hidden"] == 1

    def test_defaults(self, mock_nbt, tmp_path):
        """Verify default parameters: address, name, hidden=False."""
        out = tmp_path / "servers.dat"
        create_servers_dat(str(out))

        root_compound = mock_nbt["File"].call_args[0][0]
        entry = root_compound["servers"][0]
        assert entry["ip"] == "127.0.0.1:25565"
        assert entry["name"] == "Minecraft Server"
        assert entry["hidden"] == 0

    def test_file_save_called_with_path(self, mock_nbt, tmp_path):
        out = tmp_path / "servers.dat"
        create_servers_dat(str(out), "127.0.0.1:25565", "Test", False)

        mock_nbt["File"].return_value.save.assert_called_once_with(str(out))
