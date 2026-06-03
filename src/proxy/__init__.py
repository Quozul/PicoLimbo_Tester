"""Proxy support for routing Minecraft clients through proxies."""

from enum import Enum

from .base import ProxyManager
from .factory import ProxyFactory
from .velocity import VelocityProxyManager

__all__ = [
    "ProxyFactory",
    "ProxyType",
    "ProxyManager",
    "VelocityProxyManager",
    "get_proxy_manager",
]


class ProxyType(str, Enum):
    """Proxy type enum."""

    NONE = "none"
    VELOCITY = "velocity"
    BUNGEECORD = "bungeecord"


def get_proxy_manager(proxy_type: str) -> "ProxyManager | None":
    """Factory function to get the appropriate proxy manager.

    Args:
        proxy_type: One of "none", "velocity", "bungeecord".

    Returns:
        A ProxyManager instance, or None if proxy_type is "none" or unknown.
    """
    if proxy_type in ("none", ProxyType.NONE):
        return None
    if proxy_type in ("velocity", ProxyType.VELOCITY):
        return VelocityProxyManager()
    if proxy_type in ("bungeecord", ProxyType.BUNGEECORD):
        return None
    return None
