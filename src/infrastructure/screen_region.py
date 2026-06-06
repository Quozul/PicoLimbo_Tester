"""Anti-corruption layer for PIL/pyscreenshot screen region matching.

Wraps pyscreenshot (ImageGrab) and PIL (Image, ImageChops) to provide
a testable screen-region matching service.
"""

import logging
import os
import time

from pathlib import Path

from PIL import Image, ImageChops
import pyscreenshot as ImageGrab

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")


class ScreenRegionMatcher:
    """Wait for a screen region to match a reference image.

    Parameters
    ----------
    references_dir : str | Path
        Directory containing reference images.
    poll_interval : float
        Seconds to wait between screen captures.
    max_retries : int
        Reserved for future retry logic; not yet used.
    """

    def __init__(
        self,
        references_dir: str | Path | None = None,
        poll_interval: float = 0.5,
        max_retries: int = 3,
    ) -> None:
        self._references_dir = Path(references_dir) if references_dir else Path("references")
        self._poll_interval = poll_interval
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def wait_for_region(
        self,
        region_name: str,
        bbox: tuple[int, int, int, int],
        timeout: float = 30.0,
    ) -> bool:
        """Wait for *bbox* on screen to match any reference image.

        Parameters
        ----------
        region_name : str
            Logical name for logging/debugging; not used for file lookup.
        bbox : tuple[int, int, int, int]
            ``(x, y, width, height)`` of the screen region to watch.
        timeout : float
            Maximum seconds to wait before giving up.

        Returns
        -------
        bool
            ``True`` if a match is found; ``False`` on timeout or error.
        """
        x, y, width, height = bbox
        region_size = (width, height)
        ref_images = self._load_references(region_size)
        if not ref_images:
            logger.error("No valid reference images found in '%s'.", self._references_dir)
            return False

        logger.info(
            "Watching screen region x=%d y=%d w=%d h=%d (timeout=%.1fs, '%s')",
            x, y, width, height, timeout, region_name,
        )

        start_time = time.monotonic()
        last_capture: Image.Image | None = None

        while time.monotonic() - start_time < timeout:
            current_image = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGB")
            last_capture = current_image

            for filename, ref_image in ref_images:
                try:
                    diff = ImageChops.difference(ref_image, current_image)
                    if diff.getbbox() is None:
                        return True
                except ValueError as exc:
                    logger.warning("Error comparing images: %s", exc)

            time.sleep(self._poll_interval)

        logger.error(
            "Screen region did not match any reference image within %.1f seconds.",
            timeout,
        )
        self._save_debug_image(last_capture)
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_references(
        self, region_size: tuple[int, int]
    ) -> list[tuple[str, Image.Image]]:
        """Load and validate reference images from the references directory.

        Parameters
        ----------
        region_size : tuple[int, int]
            Expected image size ``(width, height)`` to filter on.

        Returns
        -------
        list[tuple[str, Image.Image]]
            Pairs of ``(filename, converted_image)`` whose size matches
            *region_size*.
        """
        if not self._references_dir.is_dir():
            logger.error("Reference directory not found at '%s'.", self._references_dir)
            return []

        ref_images: list[tuple[str, Image.Image]] = []
        for filename in os.listdir(self._references_dir):
            if not filename.lower().endswith(VALID_EXTENSIONS):
                continue
            try:
                path = self._references_dir / filename
                img = Image.open(path).convert("RGB")

                if img.size != region_size:
                    logger.warning(
                        "Skipping '%s' - its size %s does not match the region size %s.",
                        filename,
                        img.size,
                        region_size,
                    )
                    continue

                ref_images.append((filename, img))
            except Exception as exc:
                logger.warning("Could not load image '%s'. Error: %s", filename, exc)

        return ref_images

    def _save_debug_image(self, image: Image.Image | None) -> None:
        """Save *image* to ``current_capture.png`` for inspection."""
        if image is None:
            return
        debug_path = "current_capture.png"
        image.save(debug_path)
        logger.info("Last captured region saved to %s for inspection.", debug_path)
