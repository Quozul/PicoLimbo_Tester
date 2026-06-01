"""Minecraft version representation and support utilities.

Version is a pure immutable value object. Comparison is based on the
(major, minor, patch) tuple.

VersionSupport provides static utility methods for version-specific
feature checks (option support, LWJGL version detection).
"""

from __future__ import annotations


class Version:
    """Immutable value object representing a Minecraft version.

    Supports both string form (e.g. ``"1.21.1"``) and integer form
    (e.g. ``Version(1, 21, 1, 767)``).  Comparison is based on the
    ``major`` / ``minor`` / ``patch`` components only.

    :param major: Major version number.
    :param minor: Minor version number.
    :param patch: Patch version number.
    :param protocol_version: Minecraft protocol version number.
    """

    __slots__ = ("_major", "_minor", "_patch", "protocol_version")

    def __init__(
        self,
        major: int,
        minor: int = 0,
        patch: int = 0,
        protocol_version: int = 0,
    ) -> None:
        self._major = major
        self._minor = minor
        self._patch = patch
        self.protocol_version = protocol_version

    @classmethod
    def from_string(cls, version_str: str) -> "Version":
        """Parse a version string like ``"1.21.1"`` or ``"1.21"``.

        :param version_str: Version string in ``major.minor[.patch]`` form.
        :return: A new ``Version`` instance.
        :raises ValueError: If the string cannot be split into version parts.
        """
        parts = version_str.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return cls(major, minor, patch)

    @property
    def major(self) -> int:
        return self._major

    @property
    def minor(self) -> int:
        return self._minor

    @property
    def patch(self) -> int:
        return self._patch

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Version):
            return (self._major, self._minor, self._patch) == (
                other._major,
                other._minor,
                other._patch,
            )
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Version):
            return (self._major, self._minor, self._patch) < (
                other._major,
                other._minor,
                other._patch,
            )
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, Version):
            return (self._major, self._minor, self._patch) <= (
                other._major,
                other._minor,
                other._patch,
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._major, self._minor, self._patch))

    def __repr__(self) -> str:
        return (
            f"Version({self._major}, {self._minor}, {self._patch}, "
            f"{self.protocol_version})"
        )

    def __str__(self) -> str:
        if self._patch == 0:
            return f"{self._major}.{self._minor}"
        return f"{self._major}.{self._minor}.{self._patch}"


class VersionSupport:
    """Utility class for version-specific feature checks.

    All methods are stateless and can be used as functions or via an
    instance.  They compare against the ``(major, minor, patch)`` tuple
    so no sentinel ``Version`` objects are needed.
    """

    # -- option support thresholds ------------------------------------------

    _OPTION_SUPPORT: dict[str, tuple[int, ...]] = {
        "skipMultiplayerWarning": (1, 15, 2),
        "tutorialStep": (1, 12, 0),
        "joinedFirstServer": (1, 16, 4),
    }

    def supports_option(self, option: str, version: Version) -> bool:
        """Check if *version* supports the given option.

        :param option: Option name (``skipMultiplayerWarning``,
            ``tutorialStep``, ``joinedFirstServer``).
        :param version: Minecraft version to check.
        :return: ``True`` if the version supports the option.
        :raises ValueError: If the option name is not recognised.
        """
        threshold = self._OPTION_SUPPORT.get(option)
        if threshold is None:
            raise ValueError(f"Unsupported option: {option}")
        return (version.major, version.minor, version.patch) >= threshold

    # -- LWJGL detection ----------------------------------------------------

    def is_lwjgl2(self, version: Version) -> bool:
        """Check if *version* uses LWJGL 2.

        LWJGL 2 is used by Minecraft 1.7 – 1.12.x.  LWJGL 3 starts
        from 1.13.

        :param version: Minecraft version to check.
        :return: ``True`` if the version uses LWJGL 2.
        """
        v = (version.major, version.minor, version.patch)
        return v >= (1, 7, 0) and v < (1, 13, 0)


# ---------------------------------------------------------------------------
# Module-level data (kept for backward compatibility and as the canonical list)
# ---------------------------------------------------------------------------

ALL_VERSIONS: list[Version] = [
    Version(major=1, minor=7, patch=2, protocol_version=4),
    Version(major=1, minor=7, patch=4, protocol_version=4),
    Version(major=1, minor=7, patch=5, protocol_version=4),
    Version(major=1, minor=7, patch=6, protocol_version=5),
    Version(major=1, minor=7, patch=7, protocol_version=5),
    Version(major=1, minor=7, patch=8, protocol_version=5),
    Version(major=1, minor=7, patch=9, protocol_version=5),
    Version(major=1, minor=7, patch=10, protocol_version=5),
    Version(major=1, minor=8, patch=0, protocol_version=47),
    Version(major=1, minor=8, patch=1, protocol_version=47),
    Version(major=1, minor=8, patch=2, protocol_version=47),
    Version(major=1, minor=8, patch=3, protocol_version=47),
    Version(major=1, minor=8, patch=4, protocol_version=47),
    Version(major=1, minor=8, patch=5, protocol_version=47),
    Version(major=1, minor=8, patch=6, protocol_version=47),
    Version(major=1, minor=8, patch=7, protocol_version=47),
    Version(major=1, minor=8, patch=8, protocol_version=47),
    Version(major=1, minor=8, patch=9, protocol_version=47),
    Version(major=1, minor=9, patch=0, protocol_version=107),
    Version(major=1, minor=9, patch=1, protocol_version=108),
    Version(major=1, minor=9, patch=2, protocol_version=109),
    Version(major=1, minor=9, patch=3, protocol_version=110),
    Version(major=1, minor=9, patch=4, protocol_version=110),
    Version(major=1, minor=10, patch=0, protocol_version=210),
    Version(major=1, minor=10, patch=1, protocol_version=210),
    Version(major=1, minor=10, patch=2, protocol_version=210),
    Version(major=1, minor=11, patch=0, protocol_version=315),
    Version(major=1, minor=11, patch=1, protocol_version=316),
    Version(major=1, minor=11, patch=2, protocol_version=316),
    Version(major=1, minor=12, patch=0, protocol_version=335),
    Version(major=1, minor=12, patch=1, protocol_version=338),
    Version(major=1, minor=12, patch=2, protocol_version=340),
    Version(major=1, minor=13, patch=0, protocol_version=393),
    Version(major=1, minor=13, patch=1, protocol_version=401),
    Version(major=1, minor=13, patch=2, protocol_version=404),
    Version(major=1, minor=14, patch=0, protocol_version=477),
    Version(major=1, minor=14, patch=1, protocol_version=480),
    Version(major=1, minor=14, patch=2, protocol_version=485),
    Version(major=1, minor=14, patch=3, protocol_version=490),
    Version(major=1, minor=14, patch=4, protocol_version=498),
    Version(major=1, minor=15, patch=0, protocol_version=573),
    Version(major=1, minor=15, patch=1, protocol_version=575),
    Version(major=1, minor=15, patch=2, protocol_version=578),
    Version(major=1, minor=16, patch=0, protocol_version=735),
    Version(major=1, minor=16, patch=1, protocol_version=736),
    Version(major=1, minor=16, patch=2, protocol_version=751),
    Version(major=1, minor=16, patch=3, protocol_version=753),
    Version(major=1, minor=16, patch=4, protocol_version=754),
    Version(major=1, minor=16, patch=5, protocol_version=754),
    Version(major=1, minor=17, patch=0, protocol_version=755),
    Version(major=1, minor=17, patch=1, protocol_version=756),
    Version(major=1, minor=18, patch=0, protocol_version=757),
    Version(major=1, minor=18, patch=1, protocol_version=757),
    Version(major=1, minor=18, patch=2, protocol_version=758),
    Version(major=1, minor=19, patch=0, protocol_version=759),
    Version(major=1, minor=19, patch=1, protocol_version=760),
    Version(major=1, minor=19, patch=2, protocol_version=760),
    Version(major=1, minor=19, patch=3, protocol_version=761),
    Version(major=1, minor=19, patch=4, protocol_version=762),
    Version(major=1, minor=20, patch=0, protocol_version=763),
    Version(major=1, minor=20, patch=1, protocol_version=763),
    Version(major=1, minor=20, patch=2, protocol_version=764),
    Version(major=1, minor=20, patch=3, protocol_version=765),
    Version(major=1, minor=20, patch=4, protocol_version=765),
    Version(major=1, minor=20, patch=5, protocol_version=766),
    Version(major=1, minor=20, patch=6, protocol_version=766),
    Version(major=1, minor=21, patch=0, protocol_version=767),
    Version(major=1, minor=21, patch=1, protocol_version=767),
    Version(major=1, minor=21, patch=2, protocol_version=768),
    Version(major=1, minor=21, patch=3, protocol_version=768),
    Version(major=1, minor=21, patch=4, protocol_version=769),
    Version(major=1, minor=21, patch=5, protocol_version=770),
    Version(major=1, minor=21, patch=6, protocol_version=771),
    Version(major=1, minor=21, patch=7, protocol_version=772),
    Version(major=1, minor=21, patch=8, protocol_version=772),
    Version(major=1, minor=21, patch=9, protocol_version=773),
    Version(major=1, minor=21, patch=10, protocol_version=773),
    Version(major=1, minor=21, patch=11, protocol_version=774),
    Version(major=26, minor=1, patch=0, protocol_version=775),
    Version(major=26, minor=1, patch=1, protocol_version=775),
    Version(major=26, minor=1, patch=2, protocol_version=775),
]

# First version for each unique protocol version, derived from ALL_VERSIONS.
PROTOCOL_VERSIONS: list[Version] = [
    v
    for i, v in enumerate(ALL_VERSIONS)
    if i == 0 or v.protocol_version != ALL_VERSIONS[i - 1].protocol_version
]
