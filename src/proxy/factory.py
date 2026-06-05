"""Proxy factory for creating proxy manager instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.value_objects import ProxyType
from .base import ProxyManager

if TYPE_CHECKING:
    from src.infrastructure.config_writer import ConfigWriter

__all__ = ["ProxyFactory"]


class ProxyFactory:
    """Factory for creating proxy manager instances.

    Parameters
    ----------
    config_writer : ConfigWriter
        Shared configuration writer used by proxy managers.
    """

    def __init__(
        self,
        config_writer: "ConfigWriter",
        forwarding_secret: str | None = None,
    ) -> None:
        self._config_writer = config_writer
        self._forwarding_secret = forwarding_secret
        self._manager_map: dict[ProxyType, type[ProxyManager]] = {
            ProxyType.VELOCITY: None,  # populated lazily
        }

    def _import_velocity(self) -> type[ProxyManager]:
        """Lazy import of VelocityProxyManager to avoid circular imports."""
        from .velocity import VelocityProxyManager

        return VelocityProxyManager

    def create(self, proxy_type: ProxyType) -> ProxyManager | None:
        """Create a proxy manager for the given type.

        Parameters
        ----------
        proxy_type : ProxyType
            The type of proxy to create.

        Returns
        -------
        ProxyManager | None
            A proxy manager instance, or ``None`` for unsupported types.
        """
        if proxy_type == ProxyType.NONE:
            return None

        if proxy_type == ProxyType.VELOCITY:
            VelocityProxyManagerClass = self._import_velocity()
            return VelocityProxyManagerClass(
                config_writer=self._config_writer,
                forwarding_secret=self._forwarding_secret,
            )

        return None
