"""Server context manager for proxy + PicoLimbo subprocess lifecycle."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.proxy.base import ProxyManager

__all__ = ["ServerContext"]


class ServerContext:
    """Context manager for proxy + PicoLimbo subprocess lifecycle.

    Parameters
    ----------
    proxy : ProxyManager | None
        The proxy manager instance (may be ``None`` for direct mode).
    proxy_proc : subprocess.Popen | None
        The running proxy process (may be ``None`` for direct mode).
    pico_limbo_proc : subprocess.Popen | None
        The running PicoLimbo subprocess.
    cleanup_fn : Callable[[], None] | None
        Optional cleanup callback invoked on stop.
    """

    def __init__(
        self,
        proxy: "ProxyManager | None",
        proxy_proc: subprocess.Popen[str] | None,
        pico_limbo_proc: subprocess.Popen[str] | None,
        cleanup_fn: Callable[[], None] | None = None,
    ) -> None:
        self.proxy = proxy
        self.proxy_proc = proxy_proc
        self.pico_limbo_proc = pico_limbo_proc
        self._cleanup_fn = cleanup_fn

    def stop(self) -> None:
        """Stop proxy and PicoLimbo subprocess, run cleanup callback."""
        if self._cleanup_fn is not None:
            self._cleanup_fn()

    def __enter__(self) -> "ServerContext":
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
