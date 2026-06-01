"""Tests for ``src.versions`` — Version value object and VersionSupport."""

import pytest

from src.versions import Version, VersionSupport, ALL_VERSIONS, PROTOCOL_VERSIONS


# ---------------------------------------------------------------------------
# Module-level data tests
# ---------------------------------------------------------------------------

class TestModuleLevelData:
    def test_all_versions_is_non_empty(self):
        assert ALL_VERSIONS

    def test_all_versions_contains_expected_entries(self):
        versions_str = {str(v) for v in ALL_VERSIONS}
        assert "1.7.2" in versions_str
        assert "1.12.2" in versions_str
        assert "1.16.5" in versions_str
        assert "26.1.2" in versions_str

    def test_protocol_versions_length(self):
        assert len(PROTOCOL_VERSIONS) < len(ALL_VERSIONS)

    def test_protocol_versions_are_unique_protocol_ids(self):
        ids = [v.protocol_version for v in PROTOCOL_VERSIONS]
        assert len(ids) == len(set(ids))

    def test_protocol_versions_first_for_each_protocol(self):
        seen = set()
        for v in ALL_VERSIONS:
            if v.protocol_version not in seen:
                seen.add(v.protocol_version)
                assert v in PROTOCOL_VERSIONS

    def test_protocol_versions_count_matches_unique_protocols(self):
        unique_protocols = len({v.protocol_version for v in ALL_VERSIONS})
        assert len(PROTOCOL_VERSIONS) == unique_protocols


# ---------------------------------------------------------------------------
# Version value object — construction
# ---------------------------------------------------------------------------

class TestVersionConstruction:
    def test_integer_form_defaults(self):
        v = Version(1)
        assert v.major == 1
        assert v.minor == 0
        assert v.patch == 0
        assert v.protocol_version == 0

    def test_integer_form_all_args(self):
        v = Version(1, 12, 2, 340)
        assert v.major == 1
        assert v.minor == 12
        assert v.patch == 2
        assert v.protocol_version == 340

    def test_from_string_major_minor_patch(self):
        v = Version.from_string("1.12.2")
        assert v.major == 1
        assert v.minor == 12
        assert v.patch == 2

    def test_from_string_major_minor(self):
        v = Version.from_string("1.12")
        assert v.major == 1
        assert v.minor == 12
        assert v.patch == 0

    def test_from_string_large_major(self):
        v = Version.from_string("26.1.2")
        assert v.major == 26
        assert v.minor == 1
        assert v.patch == 2


# ---------------------------------------------------------------------------
# Version value object — string representation
# ---------------------------------------------------------------------------

class TestVersionStr:
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


class TestVersionRepr:
    def test_repr(self):
        v = Version(1, 16, 5, 754)
        assert repr(v) == "Version(1, 16, 5, 754)"

    def test_repr_patch_zero(self):
        v = Version(1, 12, 0, 335)
        assert repr(v) == "Version(1, 12, 0, 335)"


# ---------------------------------------------------------------------------
# Version value object — comparison operators
# ---------------------------------------------------------------------------

class TestVersionComparison:
    @pytest.mark.parametrize(
        "a, b, expected",
        [
            ((1, 12, 2), (1, 12, 2), True),
            ((1, 12, 2), (1, 12, 3), False),
            ((1, 12, 2), (1, 13, 0), False),
            ((1, 12, 2), (2, 0, 0), False),
        ],
    )
    def test_eq(self, a, b, expected):
        va = Version(*a, 0)
        vb = Version(*b, 0)
        assert (va == vb) is expected

    @pytest.mark.parametrize(
        "a, b",
        [
            ((1, 12, 2), (1, 12, 2)),
            ((1, 12, 2), (1, 12, 2)),
        ],
    )
    def test_eq_different_protocol_version(self, a, b):
        """protocol_version is ignored in equality."""
        va = Version(*a, 340)
        vb = Version(*b, 999)
        assert va == vb

    @pytest.mark.parametrize(
        "a, b",
        [
            ((1, 11, 0), (1, 12, 0)),
            ((1, 12, 1), (1, 12, 2)),
            ((1, 12, 0), (2, 0, 0)),
            ((1, 7, 0), (1, 13, 0)),
        ],
    )
    def test_lt(self, a, b):
        va = Version(*a, 0)
        vb = Version(*b, 0)
        assert va < vb

    @pytest.mark.parametrize(
        "a, b",
        [
            ((1, 12, 0), (1, 11, 0)),
            ((1, 12, 2), (1, 12, 1)),
            ((2, 0, 0), (1, 12, 0)),
            ((1, 13, 0), (1, 7, 0)),
        ],
    )
    def test_lt_false(self, a, b):
        va = Version(*a, 0)
        vb = Version(*b, 0)
        assert not (va < vb)

    @pytest.mark.parametrize(
        "a, b",
        [
            ((1, 11, 0), (1, 12, 0)),
            ((1, 12, 1), (1, 12, 2)),
            ((1, 12, 0), (2, 0, 0)),
            ((1, 7, 0), (1, 13, 0)),
            ((1, 12, 2), (1, 12, 2)),
        ],
    )
    def test_le(self, a, b):
        va = Version(*a, 0)
        vb = Version(*b, 0)
        assert va <= vb

    @pytest.mark.parametrize(
        "a, b",
        [
            ((1, 12, 0), (1, 11, 0)),
            ((1, 12, 2), (1, 12, 1)),
            ((2, 0, 0), (1, 12, 0)),
        ],
    )
    def test_le_false(self, a, b):
        va = Version(*a, 0)
        vb = Version(*b, 0)
        assert not (va <= vb)

    def test_hash_consistency(self):
        """Equal versions must have equal hashes."""
        a = Version(1, 12, 2, 340)
        b = Version(1, 12, 2, 999)
        assert hash(a) == hash(b)

    def test_version_in_set(self):
        versions = {Version(1, 12, 2, 340), Version(1, 12, 2, 999), Version(1, 13, 0, 393)}
        assert len(versions) == 2  # 1.12.2 entries are deduplicated

    def test_version_in_dict_key(self):
        d = {Version(1, 12, 2, 340): "hello"}
        assert d[Version(1, 12, 2, 999)] == "hello"


# ---------------------------------------------------------------------------
# VersionSupport — supports_option
# ---------------------------------------------------------------------------

class TestVersionSupportOption:
    @pytest.mark.parametrize(
        "version_str, option, expected",
        [
            ("1.15.1", "skipMultiplayerWarning", False),
            ("1.15.2", "skipMultiplayerWarning", True),
            ("1.16.5", "skipMultiplayerWarning", True),
            ("1.7.2", "skipMultiplayerWarning", False),
            ("1.11.0", "tutorialStep", False),
            ("1.12.0", "tutorialStep", True),
            ("1.16.5", "tutorialStep", True),
            ("1.16.3", "joinedFirstServer", False),
            ("1.16.4", "joinedFirstServer", True),
            ("1.16.5", "joinedFirstServer", True),
            ("1.7.2", "joinedFirstServer", False),
        ],
    )
    def test_supports_option(self, version_str, option, expected):
        v = Version.from_string(version_str)
        assert VersionSupport().supports_option(option, v) is expected

    def test_unknown_option_raises_value_error(self):
        v = Version(1, 12, 2, 340)
        with pytest.raises(ValueError, match="Unsupported option: fakeOption"):
            VersionSupport().supports_option("fakeOption", v)

    def test_unknown_option_empty_string_raises(self):
        v = Version(1, 12, 2, 340)
        with pytest.raises(ValueError, match="Unsupported option: "):
            VersionSupport().supports_option("", v)


# ---------------------------------------------------------------------------
# VersionSupport — is_lwjgl2
# ---------------------------------------------------------------------------

class TestVersionSupportLwjgl2:
    @pytest.mark.parametrize(
        "version_str, expected",
        [
            ("1.7.0", True),
            ("1.7.2", True),
            ("1.8.0", True),
            ("1.8.9", True),
            ("1.12.0", True),
            ("1.12.2", True),
            ("1.13.0", False),
            ("1.16.5", False),
            ("26.1.2", False),
        ],
    )
    def test_is_lwjgl2(self, version_str, expected):
        v = Version.from_string(version_str)
        assert VersionSupport().is_lwjgl2(v) is expected
