import argparse
import logging
import os
from typing import List

from nbtlib import File, List as NbtList, Compound, String, Byte
from versions import Version

logger = logging.getLogger(__name__)


def create_options_txt(version: Version, output_file_path: str) -> None:
    """
    Create a minimal options.txt file containing only the options supported by the given version.

    :param version: The Minecraft version to generate options for.
    :param output_file_path: Path to write the options.txt file.
    """
    logger.debug("Generating options.txt for Minecraft %s", version)

    options: List[str] = []

    if version.supports_option("skipMultiplayerWarning"):
        logger.debug("  skipMultiplayerWarning: true")
        options.append("skipMultiplayerWarning:true")

    if version.supports_option("tutorialStep"):
        logger.debug("  tutorialStep: none")
        options.append("tutorialStep:none")

    if version.supports_option("joinedFirstServer"):
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
    server_address: str,
    server_name: str = "Minecraft Server",
    hidden: bool = False,
) -> None:
    """
    Create a servers.dat NBT file containing a single server entry.

    :param output_file_path: Path to write the servers.dat file.
    :param server_address: The server address (e.g. "localhost:25565").
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


def _main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description="Minecraft Environment Tool")
    parser.add_argument(
        "--version", required=True, help="Minecraft version (e.g. 1.16.5)"
    )

    args = parser.parse_args()
    version = Version(args.version)

    logger.debug(
        "Resolved version: %s (protocol %s)", version, version.protocol_version
    )

    create_servers_dat("minecraft/servers.dat", "localhost:25565")
    create_options_txt(version, "minecraft/options.txt")


if __name__ == "__main__":
    _main()
