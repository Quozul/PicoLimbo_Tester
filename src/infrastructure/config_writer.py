"""Anti-corruption layer for configuration file generation.

Wraps nbtlib for NBT files, handles file I/O with shared helpers,
and provides TOML serialization (via tomli-w if available, otherwise
manual fallback).

Replaces direct nbtlib, TOML, and file I/O in env.py and velocity.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Sequence

from nbtlib import Compound as NbtCompound
from nbtlib import File as NbtFile
from nbtlib import List as NbtList
from nbtlib import String as NbtString
from nbtlib import Byte as NbtByte

from ..versions import Version

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Option definitions — data-driven mapping
# ---------------------------------------------------------------------------

# Each entry: (option_name, value, introduced_version)
_OPTION_DEFINITIONS: list[tuple[str, str, tuple[int, ...]]] = [
    ("skipMultiplayerWarning", "true", (1, 15, 2)),
    ("tutorialStep", "none", (1, 12, 0)),
    ("joinedFirstServer", "true", (1, 16, 4)),
]

# ---------------------------------------------------------------------------
# Server entry data class
# ---------------------------------------------------------------------------

class ServerEntry:
    """A single server entry for servers.dat."""

    __slots__ = ("ip", "name", "hidden")

    def __init__(self, ip: str, name: str = "Minecraft Server", hidden: bool = False) -> None:
        self.ip = ip
        self.name = name
        self.hidden = hidden

    @classmethod
    def from_tuple(cls, data: tuple[str, str, bool]) -> ServerEntry:
        """Create from (ip, name, hidden) tuple."""
        return cls(ip=data[0], name=data[1], hidden=data[2])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerEntry:
        """Create from a dict with ip/name/hidden keys."""
        return cls(
            ip=data["ip"],
            name=data.get("name", "Minecraft Server"),
            hidden=data.get("hidden", False),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_parent_dir(path: Path) -> None:
    """Create parent directories for *path* if they don't exist."""
    parent = path.parent
    if parent and str(parent) != "":
        os.makedirs(parent, exist_ok=True)


def _version_gte(version: Version, target: tuple[int, ...]) -> bool:
    """Check if *version* is greater than or equal to *target*."""
    return (version.major, version.minor, version.patch) >= target


def _toml_escape(value: str) -> str:
    """Escape a string for TOML basic string (double-quoted)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_value(value: Any) -> str:
    """Convert a Python value to a TOML-literal string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        items = ", ".join(_toml_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, str):
        return _toml_escape(value)
    return str(value)


def _manual_toml_dump(data: dict[str, Any], indent: int = 0) -> str:
    """Serialize a dict to TOML string (fallback when tomli-w is unavailable)."""
    lines: list[str] = []
    prefix = "  " * indent

    for key, value in data.items():
        formatted_key = key.replace("_", "-")
        if isinstance(value, dict):
            lines.append(f"{prefix}[{formatted_key}]")
            lines.append(_manual_toml_dump(value, indent + 1))
        else:
            lines.append(f"{prefix}{formatted_key} = {_toml_value(value)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ConfigWriter
# ---------------------------------------------------------------------------

class ConfigWriter:
    """Anti-corruption layer for configuration file generation.

    Wraps nbtlib for NBT files, handles file I/O with shared helpers,
    and provides TOML serialization.

    Args:
        version_support: A VersionSupport instance for version checks.
            Defaults to a fresh ``Version`` lookup.
    """

    def __init__(self, version: Version | None = None) -> None:
        self._version = version

    # -- servers.dat --------------------------------------------------------

    def write_servers_dat(
        self,
        output_path: Path,
        servers: Sequence[ServerEntry],
    ) -> None:
        """Write servers.dat using nbtlib.

        Args:
            output_path: Path to write the NBT file to.
            servers: Sequence of server entries to include.
        """
        logger.debug("Generating servers.dat with %d server(s)", len(servers))

        nbt_file = NbtFile(
            NbtCompound(
                {
                    "servers": NbtList[NbtCompound](
                        [
                            NbtCompound(
                                {
                                    "hidden": NbtByte(1 if s.hidden else 0),
                                    "ip": NbtString(s.ip),
                                    "name": NbtString(s.name),
                                }
                            )
                            for s in servers
                        ]
                    )
                }
            )
        )

        _ensure_parent_dir(output_path)
        nbt_file.save(str(output_path))

        logger.debug("Wrote servers.dat to %s", output_path)

    # -- options.txt --------------------------------------------------------

    def write_options_txt(self, output_path: Path, version: Version) -> None:
        """Write options.txt with version-appropriate options.

        Args:
            output_path: Path to write the options file to.
            version: Minecraft version to determine supported options.
        """
        logger.debug("Generating options.txt for Minecraft %s", version)

        options: list[str] = []
        for option_name, option_value, introduced in _OPTION_DEFINITIONS:
            if _version_gte(version, introduced):
                logger.debug("  %s: %s", option_name, option_value)
                options.append(f"{option_name}:{option_value}")

        _ensure_parent_dir(output_path)
        with open(output_path, "w") as f:
            f.write("\n".join(options))

        logger.debug("Wrote %d options to %s", len(options), output_path)

    # -- velocity.toml ------------------------------------------------------

    def write_velocity_toml(self, output_path: Path, config: dict[str, Any]) -> None:
        """Write velocity.toml using tomli-w or manual fallback.

        Args:
            output_path: Path to write the TOML file to.
            config: Configuration dict to serialize.
        """
        logger.debug("Generating velocity.toml")

        _ensure_parent_dir(output_path)

        try:
            import tomli_w
            with open(output_path, "wb") as f:
                tomli_w.dump(config, f)
        except ImportError:
            content = _manual_toml_dump(config)
            with open(output_path, "w") as f:
                f.write(content)

        logger.debug("Wrote velocity.toml to %s", output_path)
