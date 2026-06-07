"""Dependency injection wiring — central factory for shared instances.

This module creates and caches all shared dependencies (BuildService,
ProxyFactory, etc.) in one place. Tests can override by setting the
module-level instances directly, or by using the reset() function.

## Dependency graph
```
GitRepository ──┐
CargoBuildAdapter├──► BuildService ──┐
ArtifactStorage  ─┘                  ├──► JobOrchestrator
ConfigWriter    ──┐                  │
ProxyFactory ─────┼──► ServerSetupService
ArtifactRepository─┘
```

## Usage
```python
from src.di import get_build_service, get_proxy_factory, reset

# Production: lazy-created on first call
service = get_build_service()

# Tests: override directly
from src.di import _build_service, _proxy_factory
_build_service = MyMockBuildService()
_proxy_factory = MyMockProxyFactory()
```
"""

from __future__ import annotations

from . import config
from .application.build_service import BuildService
from .application.test_service import TestService
from .infrastructure.artifact_repository import ArtifactRepository
from .infrastructure.artifact_storage import ArtifactStorage
from .infrastructure.cargo_build import CargoBuildAdapter
from .infrastructure.config_writer import ConfigWriter
from .infrastructure.git_repository import GitRepository
from .infrastructure.minecraft_launcher import MinecraftLauncher
from .infrastructure.screen_region import ScreenRegionMatcher
from .infrastructure.window_manager import WindowManager
from .minecraft.input import VirtualInputController
from .proxy.factory import ProxyFactory

# ─── Shared instances (can be overridden by tests) ────────────────────────

_git_repo: GitRepository | None = None
_cargo: CargoBuildAdapter | None = None
_build_service: BuildService | None = None
_config_writer: ConfigWriter | None = None
_proxy_factory: ProxyFactory | None = None
_artifact_repo: ArtifactRepository | None = None
_minecraft: MinecraftLauncher | None = None
_window_manager: WindowManager | None = None
_screen_matcher: ScreenRegionMatcher | None = None
_test_service: TestService | None = None


def get_git_repo() -> GitRepository:
    """Get the shared GitRepository instance (lazy-created).

    Returns
    -------
    GitRepository
        The shared GitRepository instance.
    """
    global _git_repo
    if _git_repo is None:
        _git_repo = GitRepository(repos_dir=config.REPOS_DIR, timeout=1800.0)
    return _git_repo


def get_cargo() -> CargoBuildAdapter:
    """Get the shared CargoBuildAdapter instance (lazy-created).

    Returns
    -------
    CargoBuildAdapter
        The shared CargoBuildAdapter instance.
    """
    global _cargo
    if _cargo is None:
        _cargo = CargoBuildAdapter(timeout=1800.0, release=True)
    return _cargo


def get_build_service() -> BuildService:
    """Get the shared BuildService instance (lazy-created).

    Returns
    -------
    BuildService
        The shared BuildService instance.
    """
    global _build_service
    if _build_service is None:
        _build_service = BuildService(
            git_repo=get_git_repo(),
            cargo=get_cargo(),
            artifact_storage=ArtifactStorage(config.BUILDS_DIR),
            builds_dir=config.BUILDS_DIR,
        )
    return _build_service


def get_config_writer() -> ConfigWriter:
    """Get the shared ConfigWriter instance (lazy-created).

    Returns
    -------
    ConfigWriter
        The shared ConfigWriter instance.
    """
    global _config_writer
    if _config_writer is None:
        _config_writer = ConfigWriter()
    return _config_writer


def get_proxy_factory() -> ProxyFactory:
    """Get the shared ProxyFactory instance (lazy-created).

    Returns
    -------
    ProxyFactory
        The shared ProxyFactory instance.
    """
    global _proxy_factory
    if _proxy_factory is None:
        _proxy_factory = ProxyFactory(
            config_writer=get_config_writer(),
            forwarding_secret=config._FORWARDING_SECRET,
        )
    return _proxy_factory


def get_artifact_repo() -> ArtifactRepository:
    """Get the shared ArtifactRepository instance (lazy-created).

    Returns
    -------
    ArtifactRepository
        The shared ArtifactRepository instance.
    """
    global _artifact_repo
    if _artifact_repo is None:
        _artifact_repo = ArtifactRepository(
            api_base=config.VELOCITY_API_BASE,
            cache_dir=config.PROXY_CACHE_DIR / "velocity",
        )
    return _artifact_repo


def get_minecraft() -> MinecraftLauncher:
    """Get the shared MinecraftLauncher instance (lazy-created).

    Returns
    -------
    MinecraftLauncher
        The shared MinecraftLauncher instance.
    """
    global _minecraft
    if _minecraft is None:
        _minecraft = MinecraftLauncher(
            game_directory=config.GAME_DIRECTORY,
            jvm_args=["-Xmx2G", "-Xms2G"],
            resolution=(1024, 768),
        )
    return _minecraft


def get_window_manager() -> WindowManager:
    """Get the shared WindowManager instance (lazy-created).

    Returns
    -------
    WindowManager
        The shared WindowManager instance.
    """
    global _window_manager
    if _window_manager is None:
        _window_manager = WindowManager()
    return _window_manager


def get_screen_matcher() -> ScreenRegionMatcher:
    """Get the shared ScreenRegionMatcher instance (lazy-created).

    Returns
    -------
    ScreenRegionMatcher
        The shared ScreenRegionMatcher instance.
    """
    global _screen_matcher
    if _screen_matcher is None:
        _screen_matcher = ScreenRegionMatcher()
    return _screen_matcher


def get_test_service() -> TestService:
    """Get the shared TestService instance (lazy-created).

    Returns
    -------
    TestService
        The shared TestService instance.
    """
    global _test_service
    if _test_service is None:
        _test_service = TestService(
            minecraft=get_minecraft(),
            window_manager=get_window_manager(),
            screen_matcher=get_screen_matcher(),
            input_controller=VirtualInputController(),
            screenshots_dir=config.SCREENSHOTS_DIR,
        )
    return _test_service


def reset() -> None:
    """Reset all shared instances.

    Useful in tests to ensure isolation between test runs.
    """
    global _git_repo, _cargo, _build_service, _config_writer, _proxy_factory, _artifact_repo
    global _minecraft, _window_manager, _screen_matcher, _test_service
    _git_repo = None
    _cargo = None
    _build_service = None
    _config_writer = None
    _proxy_factory = None
    _artifact_repo = None
    _minecraft = None
    _window_manager = None
    _screen_matcher = None
    _test_service = None


__all__ = [
    "get_git_repo",
    "get_cargo",
    "get_build_service",
    "get_config_writer",
    "get_proxy_factory",
    "get_artifact_repo",
    "get_minecraft",
    "get_window_manager",
    "get_screen_matcher",
    "get_test_service",
    "reset",
]
