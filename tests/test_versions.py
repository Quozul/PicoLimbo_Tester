import pytest
from unittest.mock import patch

from src.versions import Version, ALL_VERSIONS, PROTOCOL_VERSIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimal ALL_VERSIONS for string-form tests where we don't care about the
# full history.  We patch it so that `Version.__new__` can look up
# protocol_version without depending on the real (large) list.
_MINIMAL_VERSIONS = [
    Version(major=1, minor=7, patch=0, protocol_version=5),
    Version(major=1, minor=7, patch=2, protocol_version=5),
    Version(major=1, minor=8, patch=0, protocol_version=47),
    Version(major=1, minor=11, patch=0, protocol_version=315),
    Version(major=1, minor=12, patch=0, protocol_version=335),
    Version(major=1, minor=12, patch=2, protocol_version=340),
    Version(major=1, minor=13, patch=0, protocol_version=393),
    Version(major=1, minor=15, patch=1, protocol_version=575),
    Version(major=1, minor=15, patch=2, protocol_version=578),
    Version(major=1, minor=16, patch=3, protocol_version=753),
    Version(major=1, minor=16, patch=4, protocol_version=754),
    Version(major=1, minor=16, patch=5, protocol_version=754),
    Version(major=1, minor=17, patch=0, protocol_version=755),
    Version(major=26, minor=1, patch=2, protocol_version=775),
]


# ---------------------------------------------------------------------------
# ALL_VERSIONS / PROTOCOL_VERSIONS module-level checks
# ---------------------------------------------------------------------------

class TestModuleLevelData:
    def test_all_versions_is_non_empty(self):
        assert ALL_VERSIONS, "ALL_VERSIONS should not be empty"

    def test_all_versions_contains_expected_entries(self):
        """Check that some well-known versions are present."""
        versions_str = {str(v) for v in ALL_VERSIONS}
        assert "1.7.2" in versions_str
        assert "1.12.2" in versions_str
        assert "1.16.5" in versions_str
        assert "26.1.2" in versions_str

    def test_protocol_versions_length(self):
        """PROTOCOL_VERSIONS should have fewer entries than ALL_VERSIONS."""
        assert len(PROTOCOL_VERSIONS) < len(ALL_VERSIONS)

    def test_protocol_versions_are_unique_protocol_ids(self):
        """Each entry in PROTOCOL_VERSIONS should have a distinct protocol_version."""
        ids = [v.protocol_version for v in PROTOCOL_VERSIONS]
        assert len(ids) == len(set(ids))

    def test_protocol_versions_first_for_each_protocol(self):
        """The first ALL_VERSIONS entry with a given protocol_version must be
        present in PROTOCOL_VERSIONS."""
        seen = set()
        for v in ALL_VERSIONS:
            if v.protocol_version not in seen:
                seen.add(v.protocol_version)
                assert v in PROTOCOL_VERSIONS

    def test_protocol_versions_count_matches_unique_protocols(self):
        unique_protocols = len({v.protocol_version for v in ALL_VERSIONS})
        assert len(PROTOCOL_VERSIONS) == unique_protocols


# ---------------------------------------------------------------------------
# __str__
# ---------------------------------------------------------------------------

class TestStr:
    def test_patch_zero(self):
        v = Version(1, 12, 0, 335)
        assert str(v) == "1.12"

    def test_patch_nonzero(self):
        v = Version(1, 16, 5, 754)
        assert str(v) == "1.16.5"

    def test_patch_zero_17(self):
        v = Version(1, 17, 0, 755)
        assert str(v) == "1.17"

    def test_large_major(self):
        v = Version(26, 1, 0, 775)
        assert str(v) == "26.1"


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr(self):
        v = Version(1, 16, 5, 754)
        assert repr(v) == "Version(1, 16, 5, 754)"

    def test_repr_patch_zero(self):
        v = Version(1, 12, 0, 335)
        assert repr(v) == "Version(1, 12, 0, 335)"


# ---------------------------------------------------------------------------
# _cmp
# ---------------------------------------------------------------------------

class TestCmp:
    def test_equal(self):
        a = Version(1, 12, 2, 340)
        b = Version(1, 12, 2, 340)
        assert a._cmp(b) == 0

    def test_less_than_minor(self):
        a = Version(1, 11, 0, 315)
        b = Version(1, 12, 0, 335)
        assert a._cmp(b) == -1

    def test_less_than_patch(self):
        a = Version(1, 12, 1, 338)
        b = Version(1, 12, 2, 340)
        assert a._cmp(b) == -1

    def test_less_than_major(self):
        a = Version(1, 12, 0, 335)
        b = Version(2, 0, 0, 1000)
        assert a._cmp(b) == -1

    def test_greater_than(self):
        a = Version(1, 16, 5, 754)
        b = Version(1, 12, 2, 340)
        assert a._cmp(b) == 1

    def test_protocol_version_ignored_in_comparison(self):
        a = Version(1, 12, 2, 340)
        b = Version(1, 12, 2, 999)
        assert a._cmp(b) == 0


# ---------------------------------------------------------------------------
# supports_option
# ---------------------------------------------------------------------------

class TestSupportsOption:
    # -- skipMultiplayerWarning (1.15.2+) ----------------------------------

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_skip_multiplayer_warning_before_1_15_2(self):
        v = Version("1.15.1")
        assert v.supports_option("skipMultiplayerWarning") is False

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_skip_multiplayer_warning_at_1_15_2(self):
        v = Version("1.15.2")
        assert v.supports_option("skipMultiplayerWarning") is True

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_skip_multiplayer_warning_after_1_15_2(self):
        v = Version("1.16.5")
        assert v.supports_option("skipMultiplayerWarning") is True

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_skip_multiplayer_warning_very_old(self):
        v = Version("1.7.2")
        assert v.supports_option("skipMultiplayerWarning") is False

    # -- tutorialStep (1.12+) ----------------------------------------------

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_tutorial_step_at_1_12_0(self):
        v = Version("1.12")
        assert v.supports_option("tutorialStep") is True

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_tutorial_step_before_1_12(self):
        v = Version("1.11.0")
        assert v.supports_option("tutorialStep") is False

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_tutorial_step_after_1_12(self):
        v = Version("1.16.5")
        assert v.supports_option("tutorialStep") is True

    # -- joinedFirstServer (1.16.4+) ---------------------------------------

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_joined_first_server_at_1_16_4(self):
        v = Version("1.16.4")
        assert v.supports_option("joinedFirstServer") is True

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_joined_first_server_at_1_16_5(self):
        v = Version("1.16.5")
        assert v.supports_option("joinedFirstServer") is True

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_joined_first_server_before_1_16_4(self):
        v = Version("1.16.3")
        assert v.supports_option("joinedFirstServer") is False

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_joined_first_server_very_old(self):
        v = Version("1.7.2")
        assert v.supports_option("joinedFirstServer") is False

    # -- unknown option name ------------------------------------------------

    def test_unknown_option_raises_value_error(self):
        v = Version(1, 12, 2, 340)
        with pytest.raises(ValueError, match="Unsupported option: fakeOption"):
            v.supports_option("fakeOption")

    def test_unknown_option_empty_string_raises(self):
        v = Version(1, 12, 2, 340)
        with pytest.raises(ValueError, match="Unsupported option: "):
            v.supports_option("")


# ---------------------------------------------------------------------------
# is_lwjgl2
# ---------------------------------------------------------------------------

class TestIsLwjgl2:
    def test_lwjgl2_1_7(self):
        v = Version(1, 7, 0, 5)
        assert v.is_lwjgl2() is True

    def test_lwjgl2_1_7_2(self):
        v = Version(1, 7, 2, 4)
        assert v.is_lwjgl2() is True

    def test_lwjgl2_1_8(self):
        v = Version(1, 8, 0, 47)
        assert v.is_lwjgl2() is True

    def test_lwjgl2_1_12_0(self):
        v = Version(1, 12, 0, 335)
        assert v.is_lwjgl2() is True

    def test_lwjgl2_1_12_2(self):
        v = Version(1, 12, 2, 340)
        assert v.is_lwjgl2() is True

    def test_lwjgl3_1_13(self):
        v = Version(1, 13, 0, 393)
        assert v.is_lwjgl2() is False

    def test_lwjgl3_1_16(self):
        v = Version(1, 16, 5, 754)
        assert v.is_lwjgl2() is False

    def test_lwjgl3_new_version(self):
        v = Version(26, 1, 2, 775)
        assert v.is_lwjgl2() is False


# ---------------------------------------------------------------------------
# Construction: string form
# ---------------------------------------------------------------------------

class TestStringForm:
    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_major_minor_patch(self):
        v = Version("1.12.2")
        assert v.major == 1
        assert v.minor == 12
        assert v.patch == 2
        assert v.protocol_version == 340

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_major_minor(self):
        v = Version("1.12")
        assert v.major == 1
        assert v.minor == 12
        assert v.patch == 0
        assert v.protocol_version == 335

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_unknown_version_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown version: 9.9.9"):
            Version("9.9.9")

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_major_26(self):
        v = Version("26.1.2")
        assert v.major == 26
        assert v.minor == 1
        assert v.patch == 2
        assert v.protocol_version == 775


# ---------------------------------------------------------------------------
# Construction: integer form
# ---------------------------------------------------------------------------

class TestIntegerForm:
    def test_all_args_provided(self):
        v = Version(1, 12, 2, 340)
        assert v.major == 1
        assert v.minor == 12
        assert v.patch == 2
        assert v.protocol_version == 340

    def test_missing_minor_raises_type_error(self):
        with pytest.raises(TypeError, match="Version\\(\\) requires all arguments"):
            Version(1)

    def test_missing_patch_raises_type_error(self):
        with pytest.raises(TypeError, match="Version\\(\\) requires all arguments"):
            Version(1, 12)

    def test_missing_protocol_version_raises_type_error(self):
        with pytest.raises(TypeError, match="Version\\(\\) requires all arguments"):
            Version(1, 12, 2)

    def test_all_missing_raises_type_error(self):
        # Python's own TypeError fires for missing 'major' before our
        # validation logic runs.  We just confirm a TypeError is raised.
        with pytest.raises(TypeError):
            Version()


# ---------------------------------------------------------------------------
# Round-trip: __str__ + string form
# ---------------------------------------------------------------------------

class TestRoundTrip:
    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_str_roundtrip_with_patch(self):
        v = Version("1.12.2")
        v2 = Version(str(v))
        assert v.major == v2.major
        assert v.minor == v2.minor
        assert v.patch == v2.patch
        assert v.protocol_version == v2.protocol_version

    @patch("src.versions.ALL_VERSIONS", _MINIMAL_VERSIONS)
    def test_str_roundtrip_without_patch(self):
        v = Version("1.12")
        v2 = Version(str(v))
        assert v.major == v2.major
        assert v.minor == v2.minor
        assert v.patch == v2.patch
        assert v.protocol_version == v2.protocol_version
