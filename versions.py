class Version:
    def __new__(cls, major: int | str, minor: int | None = None, patch: int | None = None, protocol_version: int | None = None):
        """
        Create a Version instance.

        Two usage patterns:

        1. **String form** — automatically looks up the protocol version::

            >>> Version("1.16.5")
            Version(1, 16, 5, 754)
            >>> Version("26.1.2")
            Version(26, 1, 2, 775)

            Accepts "major.minor" or "major.minor.patch". Raises ``ValueError``
            if the version is not in ``ALL_VERSIONS``.

        2. **Integer form** — all four arguments required::

            >>> Version(1, 12, 2, 340)
            Version(1, 12, 2, 340)

            Raises ``TypeError`` if any of ``minor``, ``patch``, or
            ``protocol_version`` is omitted.

        :param major: Major version number (int) or full version string (e.g. "1.16.5")
        :param minor: Minor version number (int, required for integer form)
        :param patch: Patch version number (int, required for integer form)
        :param protocol_version: Minecraft protocol version (int, required for integer form)
        :return: A new Version instance
        :raises ValueError: If the version string is not found in ALL_VERSIONS
        :raises TypeError: If integer form is used without all three remaining arguments
        """
        if isinstance(major, str):
            # String form: "1.16.5" or "1.16"
            parts = major.split(".")
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2]) if len(parts) > 2 else 0

            # Look up protocol version from ALL_VERSIONS
            for v in ALL_VERSIONS:
                if v.major == major and v.minor == minor and v.patch == patch:
                    protocol_version = v.protocol_version
                    break
            if protocol_version is None:
                raise ValueError(
                    f"Unknown version: {major}.{minor}.{patch}. "
                    f"Supported versions: {', '.join(str(v) for v in ALL_VERSIONS)}"
                )

        if minor is None or patch is None or protocol_version is None:
            raise TypeError(
                "Version() requires all arguments when called with integers: "
                "Version(major, minor, patch, protocol_version)"
            )

        instance = super().__new__(cls)
        instance.major = major
        instance.minor = minor
        instance.patch = patch
        instance.protocol_version = protocol_version
        return instance

    def __repr__(self):
        return f"Version({self.major}, {self.minor}, {self.patch}, {self.protocol_version})"

    def __str__(self):
        if self.patch == 0:
            return str(self.major) + "." + str(self.minor)
        return str(self.major) + "." + str(self.minor) + "." + str(self.patch)

    def _cmp(self, other: "Version") -> int:
        """Compare this version with another. Returns -1, 0, or 1."""
        if (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        ):
            return -1
        elif (self.major, self.minor, self.patch) > (
            other.major,
            other.minor,
            other.patch,
        ):
            return 1
        return 0

    def supports_option(self, option_name: str) -> bool:
        """
        This method checks if the given option is supported.
        Only supports the following option names:
            - skipMultiplayerWarning, introduced in 1.15.2
            - tutorialStep, introduced in 1.12
            - joinedFirstServer, introduced in 1.16.4
        :param option_name: The name of the option
        :return: If the option is supported
        """
        if option_name == "skipMultiplayerWarning":
            return self._cmp(Version(1, 15, 2, 0)) >= 0
        elif option_name == "tutorialStep":
            return self._cmp(Version(1, 12, 0, 0)) >= 0
        elif option_name == "joinedFirstServer":
            return self._cmp(Version(1, 16, 4, 754)) >= 0
        raise ValueError(f"Unsupported option: {option_name}")

    def is_lwjgl2(self) -> bool:
        """
        LWJGL 2 is used by Minecraft 1.7–1.12.X.
        LWJGL 3 is used starting 1.13.

        :return: If the version supports LWJGL 2
        """
        return self._cmp(Version(1, 7, 0, 0)) >= 0 > self._cmp(Version(1, 13, 0, 0))


ALL_VERSIONS = [
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
PROTOCOL_VERSIONS = [
    v
    for i, v in enumerate(ALL_VERSIONS)
    if i == 0 or v.protocol_version != ALL_VERSIONS[i - 1].protocol_version
]
