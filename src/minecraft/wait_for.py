"""Screen-region waiting utilities — delegates to :class:`ScreenRegionMatcher`."""

import logging

from src.infrastructure.screen_region import ScreenRegionMatcher

logger = logging.getLogger(__name__)


def wait_for_screen_region(
    reference_images_dir: str,
    region: tuple[int, int, int, int],
    timeout: float = 30.0,
    interval: float = 0.5,
) -> bool:
    """Wait for a screen region to match any reference image.

    .. deprecated::
        Use :class:`src.infrastructure.screen_region.ScreenRegionMatcher`
        directly for new code.

    Parameters
    ----------
    reference_images_dir : str
        Path to the directory containing reference images.
    region : tuple[int, int, int, int]
        ``(x, y, width, height)`` of the screen region to watch.
    timeout : float
        Maximum seconds to wait.
    interval : float
        Seconds between screen captures.

    Returns
    -------
    bool
        ``True`` if a match is found within *timeout*.
    """
    matcher = ScreenRegionMatcher(
        references_dir=reference_images_dir,
        poll_interval=interval,
    )
    return matcher.wait_for_region("deprecated", region, timeout=timeout)
