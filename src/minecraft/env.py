"""Minecraft environment setup: servers.dat and options.txt generation.

Provides both the legacy module-level functions (for backward compatibility)
and a ``ConfigWriter`` instance for injection-based usage.
"""

import logging
import os
from typing import List

from nbtlib import File, List as NbtList, Compound, String, Byte
from .. import config
from ..versions import Version, VersionSupport

logger = logging.getLogger(__name__)


def create_options_txt(version: Version, output_file_path: str) -> None:
    """
    Create a minimal options.txt file containing only the options supported by the given version.

    :param version: The Minecraft version to generate options for.
    :param output_file_path: Path to write the options.txt file.
    """
    logger.debug("Generating options.txt for Minecraft %s", version)

    options: List[str] = []
    support = VersionSupport()

    if support.supports_option("skipMultiplayerWarning", version):
        logger.debug("  skipMultiplayerWarning: true")
        options.append("skipMultiplayerWarning:true")

    if support.supports_option("tutorialStep", version):
        logger.debug("  tutorialStep: none")
        options.append("tutorialStep:none")

    if support.supports_option("joinedFirstServer", version):
        logger.debug("  joinedFirstServer: true")
        options.append("joinedFirstServer:true")

    parent_dir = os.path.dirname(output_file_path)
    if parent_dir != "":
        os.makedirs(parent_dir, exist_ok=True)
    with open(output_file_path, "w") as f:
        f.write("\n".join(options))

    logger.debug("Wrote %d options to %s", len(options), output_file_path)


def create_servers_dat(
    output_file_path: str,
    server_address: str = "127.0.0.1:25565",
    server_name: str = "Minecraft Server",
    hidden: bool = False,
) -> None:
    """
    Create a servers.dat NBT file containing a single server entry.

    :param output_file_path: Path to write the servers.dat file.
    :param server_address: The server address (e.g. "127.0.0.1:25565").
    :param server_name: The display name for the server.
    :param hidden: Whether the server should be hidden.
    """
    logger.debug("Generating servers.dat for %s (%s)", server_address, server_name)

    nbt_file = File(
        Compound(
            {
                "servers": NbtList[Compound](
                    [
                        Compound(
                            {
                                "hidden": Byte(1 if hidden else 0),
                                "ip": String(server_address),
                                "name": String(server_name),
                            }
                        )
                    ]
                )
            }
        )
    )

    parent_dir = os.path.dirname(output_file_path)
    if parent_dir != "":
        os.makedirs(parent_dir, exist_ok=True)
    nbt_file.save(output_file_path)

    logger.debug("Wrote servers.dat to %s", output_file_path)


# -- Public API for injection-based usage -----------------------------------

from ..infrastructure.config_writer import ConfigWriter, ServerEntry

# Shared instance for direct use
config_writer = ConfigWriter()


def write_servers_dat(
    output_path,
    servers,
):
    """Write servers.dat using the shared ConfigWriter instance.

    Convenience wrapper for injection-based usage.
    """
    config_writer.write_servers_dat(output_path, servers)


def write_options_txt(output_path, version: Version):
    """Write options.txt using the shared ConfigWriter instance.

    Convenience wrapper for injection-based usage.
    """
    config_writer.write_options_txt(output_path, version)


def write_velocity_toml(output_path, config_dict):
    """Write velocity.toml using the shared ConfigWriter instance.

    Convenience wrapper for injection-based usage.
    """
    config_writer.write_velocity_toml(output_path, config_dict)
