"""Centralized configuration — all magic constants, paths, timeouts, and hardcoded values.

This module consolidates configuration values that are scattered across the codebase.
Each constant has a docstring explaining its purpose. Values use sensible defaults
but can be overridden by injecting them at runtime.

Naming convention: UPPERCASE for module-level constants.
Grouping: Related constants are grouped together with comment headers.
"""

from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

# Directory where cloned git repositories are stored
REPOS_DIR = Path("/app/repos")

# Directory where build artifacts (compiled binaries) are stored
BUILDS_DIR = Path("/app/builds")

# Minecraft game directory — where minecraft_launcher_lib installs and runs the game
GAME_DIRECTORY = Path("/app/minecraft")

# Directory for screenshot reports generated during integration tests
SCREENSHOTS_DIR = Path("/app/integration_tests_reports")

# Proxy cache directory — stores downloaded proxy JARs (e.g. Velocity)
PROXY_CACHE_DIR = Path("/app/cache/proxies")

# Directory containing plugin JAR files to be copied into the proxy's plugins/ folder
PLUGINS_DIR = Path("/app/plugins")

# Directory for embedded web UI static assets
_SRC_DIR = Path(__file__).resolve().parent
WEBUI_DIR = _SRC_DIR.parent / "webui-dist"

# SQLite database path for job persistence
DB_PATH = Path("/app/builds/jobs.db")

# ─── Network / Addresses ─────────────────────────────────────────────────────

# PicoLimbo server bind address (loopback)
SERVER_ADDRESS = "127.0.0.1:25565"

# Internal port PicoLimbo binds to when a proxy (e.g. Velocity) is in front of it
PICO_LIMBO_INTERNAL_PORT = 30066

# PaperMC API base URL for fetching Velocity builds
VELOCITY_API_BASE = "https://fill.papermc.io/v3/projects/velocity"

# ─── Security / Secrets ──────────────────────────────────────────────────────

# Forwarding secret used by Velocity and PicoLimbo for player-info forwarding.
# SECURITY: In production, this should be loaded from an environment variable
# or a secrets manager. Hardcoded here only for test/development convenience.
_FORWARDING_SECRET = "sup3r-s3cr3t"

# ─── Timeouts ─────────────────────────────────────────────────────────────────

# Estimated seconds per Minecraft version test (used for ETA calculation)
SECONDS_PER_VERSION = 90

# Timeout in seconds for git operations (cargo build, etc.)
GIT_CARGO_TIMEOUT = 1800.0  # 30 minutes

# Timeout in seconds for waiting for PicoLimbo to start listening
PICO_LIMBO_START_TIMEOUT = 30.0

# Timeout in seconds for waiting for Velocity proxy to be ready
PROXY_START_TIMEOUT = 30.0

# Timeout in seconds for waiting for a Minecraft window to appear
MINECRAFT_WINDOW_TIMEOUT = 120.0

# Timeout in seconds for waiting for screen region match
SCREEN_REGION_TIMEOUT = 15.0

# Timeout in seconds between screen region checks
SCREEN_REGION_INTERVAL = 0.5

# ─── JVM / Launcher ──────────────────────────────────────────────────────────

# Default JVM arguments for Minecraft launcher
JVM_ARGS = ["-Xmx2G", "-Xms2G"]

# Default Minecraft window resolution (width, height)
RESOLUTION = (1024, 768)

# ─── Click Coordinates ───────────────────────────────────────────────────────

# Absolute click coordinates within the 1024x768 Minecraft window.
# Used by log_to_multiplayer() to navigate the UI.

# "Multiplayer" button center
CLICK_MULTIPLAYER = (507, 438)

# "Join Server" button center
CLICK_JOIN_SERVER = (201, 630)

# Server button coordinates — different for 1.7.x vs 1.8+
CLICK_SERVER_BUTTON_1_7 = (507, 264)
CLICK_SERVER_BUTTON_1_8_PLUS = (507, 146)

# ─── Quit Button Regions ─────────────────────────────────────────────────────

# Bounding box (x, y, width, height) for the "Quit Game" button on modern Minecraft (LWJGL 3+).
# Used to detect when the main menu has loaded.
_QUIT_REGION_NEWER = (519, 588, 294, 60)

# Bounding box for older Minecraft (LWJGL 2, versions 1.7–1.12).
# Coordinates differ slightly due to different GUI rendering.
_QUIT_REGION_OLDER = (517, 600, 294, 60)

# ─── PicoLimbo Server Config ─────────────────────────────────────────────────

# Default PicoLimbo config content for direct (no-proxy) mode
SERVER_CONFIG_CONTENT = 'bind = "0.0.0.0:25565"\n'

# ─── Proxy ────────────────────────────────────────────────────────────────────

# Velocity config file name
VELOCITY_CONFIG_FILENAME = "velocity.toml"

# ─── Velocity Forwarding Method Mapping ──────────────────────────────────────

# Map Velocity forwarding method names to PicoLimbo forwarding method names
_VELOCITY_TO_PICOLIMBO_METHOD = {
    "none": "NONE",
    "legacy": "LEGACY",
    "bungeeguard": "BUNGEE_GUARD",
    "modern": "MODERN",
}

# ─── nbtlib Type Mappings ───────────────────────────────────────────────────

# NBT type mappings for creating servers.dat files via nbtlib.
# Maps logical field names to their NBT types and default values.
NBT_FIELD_TYPES = {
    "hidden": ("Byte", lambda h: 1 if h else 0),
    "ip": "String",
    "name": "String",
}

# ─── Config Factory ──────────────────────────────────────────────────────────

class Config:
    """Runtime-configurable configuration container.

    Use this class when you need to override defaults (e.g. in tests).
    Create an instance and pass it around instead of importing module-level constants.

    Example:
        config = Config(
            repos_dir=Path("/tmp/repos"),
            builds_dir=Path("/tmp/builds"),
        )
    """

    def __init__(
        self,
        repos_dir: Path | None = None,
        builds_dir: Path | None = None,
        game_directory: Path | None = None,
        screenshots_dir: Path | None = None,
        proxy_cache_dir: Path | None = None,
        plugins_dir: Path | None = None,
        webui_dir: Path | None = None,
        db_path: Path | None = None,
        server_address: str | None = None,
        pico_limbo_internal_port: int | None = None,
        velocity_api_base: str | None = None,
        forwarding_secret: str | None = None,
        seconds_per_version: int | None = None,
        git_cargo_timeout: float | None = None,
        pico_limbo_start_timeout: float | None = None,
        proxy_start_timeout: float | None = None,
        minecraft_window_timeout: float | None = None,
        screen_region_timeout: float | None = None,
        screen_region_interval: float | None = None,
        jvm_args: list[str] | None = None,
        resolution: tuple[int, int] | None = None,
        click_multiplayer: tuple[int, int] | None = None,
        click_join_server: tuple[int, int] | None = None,
        click_server_button_1_7: tuple[int, int] | None = None,
        click_server_button_1_8_plus: tuple[int, int] | None = None,
        quit_region_newer: tuple[int, int, int, int] | None = None,
        quit_region_older: tuple[int, int, int, int] | None = None,
        server_config_content: str | None = None,
        velocity_config_filename: str | None = None,
    ):
        """Initialize config with defaults, then override with provided values."""
        self._repos_dir = repos_dir or REPOS_DIR
        self._builds_dir = builds_dir or BUILDS_DIR
        self._game_directory = game_directory or GAME_DIRECTORY
        self._screenshots_dir = screenshots_dir or SCREENSHOTS_DIR
        self._proxy_cache_dir = proxy_cache_dir or PROXY_CACHE_DIR
        self._plugins_dir = plugins_dir or PLUGINS_DIR
        self._webui_dir = webui_dir or WEBUI_DIR
        self._db_path = db_path or DB_PATH
        self._server_address = server_address or SERVER_ADDRESS
        self._pico_limbo_internal_port = pico_limbo_internal_port or PICO_LIMBO_INTERNAL_PORT
        self._velocity_api_base = velocity_api_base or VELOCITY_API_BASE
        self._forwarding_secret = forwarding_secret or _FORWARDING_SECRET
        self._seconds_per_version = seconds_per_version or SECONDS_PER_VERSION
        self._git_cargo_timeout = git_cargo_timeout or GIT_CARGO_TIMEOUT
        self._pico_limbo_start_timeout = pico_limbo_start_timeout or PICO_LIMBO_START_TIMEOUT
        self._proxy_start_timeout = proxy_start_timeout or PROXY_START_TIMEOUT
        self._minecraft_window_timeout = minecraft_window_timeout or MINECRAFT_WINDOW_TIMEOUT
        self._screen_region_timeout = screen_region_timeout or SCREEN_REGION_TIMEOUT
        self._screen_region_interval = screen_region_interval or SCREEN_REGION_INTERVAL
        self._jvm_args = jvm_args or JVM_ARGS
        self._resolution = resolution or RESOLUTION
        self._click_multiplayer = click_multiplayer or CLICK_MULTIPLAYER
        self._click_join_server = click_join_server or CLICK_JOIN_SERVER
        self._click_server_button_1_7 = click_server_button_1_7 or CLICK_SERVER_BUTTON_1_7
        self._click_server_button_1_8_plus = click_server_button_1_8_plus or CLICK_SERVER_BUTTON_1_8_PLUS
        self._quit_region_newer = quit_region_newer or _QUIT_REGION_NEWER
        self._quit_region_older = quit_region_older or _QUIT_REGION_OLDER
        self._server_config_content = server_config_content or SERVER_CONFIG_CONTENT
        self._velocity_config_filename = velocity_config_filename or VELOCITY_CONFIG_FILENAME

    @property
    def repos_dir(self) -> Path:
        return self._repos_dir

    @property
    def builds_dir(self) -> Path:
        return self._builds_dir

    @property
    def game_directory(self) -> Path:
        return self._game_directory

    @property
    def screenshots_dir(self) -> Path:
        return self._screenshots_dir

    @property
    def proxy_cache_dir(self) -> Path:
        return self._proxy_cache_dir

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    @property
    def webui_dir(self) -> Path:
        return self._webui_dir

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def server_address(self) -> str:
        return self._server_address

    @property
    def pico_limbo_internal_port(self) -> int:
        return self._pico_limbo_internal_port

    @property
    def velocity_api_base(self) -> str:
        return self._velocity_api_base

    @property
    def forwarding_secret(self) -> str:
        return self._forwarding_secret

    @property
    def seconds_per_version(self) -> int:
        return self._seconds_per_version

    @property
    def git_cargo_timeout(self) -> float:
        return self._git_cargo_timeout

    @property
    def pico_limbo_start_timeout(self) -> float:
        return self._pico_limbo_start_timeout

    @property
    def proxy_start_timeout(self) -> float:
        return self._proxy_start_timeout

    @property
    def minecraft_window_timeout(self) -> float:
        return self._minecraft_window_timeout

    @property
    def screen_region_timeout(self) -> float:
        return self._screen_region_timeout

    @property
    def screen_region_interval(self) -> float:
        return self._screen_region_interval

    @property
    def jvm_args(self) -> list[str]:
        return self._jvm_args

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    @property
    def click_multiplayer(self) -> tuple[int, int]:
        return self._click_multiplayer

    @property
    def click_join_server(self) -> tuple[int, int]:
        return self._click_join_server

    @property
    def click_server_button_1_7(self) -> tuple[int, int]:
        return self._click_server_button_1_7

    @property
    def click_server_button_1_8_plus(self) -> tuple[int, int]:
        return self._click_server_button_1_8_plus

    @property
    def quit_region_newer(self) -> tuple[int, int, int, int]:
        return self._quit_region_newer

    @property
    def quit_region_older(self) -> tuple[int, int, int, int]:
        return self._quit_region_older

    @property
    def server_config_content(self) -> str:
        return self._server_config_content

    @property
    def velocity_config_filename(self) -> str:
        return self._velocity_config_filename
