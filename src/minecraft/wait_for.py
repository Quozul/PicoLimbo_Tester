import logging
import os
import time

from PIL import Image, ImageChops
import pyscreenshot as ImageGrab

logger = logging.getLogger(__name__)


def wait_for_screen_region(
    reference_images_dir: str,
    region: tuple[int, int, int, int],
    timeout: float = 30.0,
    interval: float = 0.5,
) -> bool:
    """
    Waits for a specified screen region to match any of the reference images
    in a given directory.

    Args:
        reference_images_dir: Path to the directory containing reference images.
        region: A tuple (x, y, width, height) defining the screen area to watch.
        timeout: Maximum time in seconds to wait for a match.
        interval: Time in seconds to wait between screen checks.

    Returns:
        True if a match is found within the timeout, False otherwise.
    """
    if not os.path.isdir(reference_images_dir):
        logger.error("Reference directory not found at '%s'", reference_images_dir)
        return False

    # --- Pre-load and validate reference images ---
    valid_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
    ref_images = []
    region_size = (region[2], region[3])

    for filename in os.listdir(reference_images_dir):
        if filename.lower().endswith(valid_extensions):
            try:
                path = os.path.join(reference_images_dir, filename)
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
            except Exception as e:
                logger.warning("Could not load image '%s'. Error: %s", filename, e)

    if not ref_images:
        logger.error(
            "No valid reference images found in '%s' that match the region size.",
            reference_images_dir,
        )
        return False
    # --- End of pre-loading ---

    start_time = time.monotonic()
    x, y, width, height = region
    logger.info(
        "Watching screen region x=%d y=%d w=%d h=%d (timeout=%.1fs)",
        x, y, width, height, timeout,
    )
    last_capture: Image.Image | None = None

    while time.monotonic() - start_time < timeout:
        # Grab the current screen content in the specified region
        current_image = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert(
            "RGB"
        )
        last_capture = current_image

        # Compare the current screen against each pre-loaded reference image
        for filename, ref_image in ref_images:
            try:
                diff = ImageChops.difference(ref_image, current_image)
                if diff.getbbox() is None:
                    return True
            except ValueError as e:
                # This might happen if image modes are different, though .convert("RGB") should prevent it
                logger.warning("Error comparing images: %s", e)

        # Wait before the next check
        time.sleep(interval)

    logger.error(
        "Screen region did not match any reference image within %.1f seconds.", timeout
    )
    if last_capture is not None:
        debug_path = "current_capture.png"
        last_capture.save(debug_path)
        logger.info("Last captured region saved to %s for inspection.", debug_path)
    return False
