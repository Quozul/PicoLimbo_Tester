import os
import time
from PIL import Image, ImageChops
import pyscreenshot as ImageGrab


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
        print(f"Error: Reference directory not found at '{reference_images_dir}'")
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
                    print(
                        f"Warning: Skipping '{filename}' - its size {img.size} does not "
                        f"match the region size {region_size}."
                    )
                    continue

                ref_images.append((filename, img))
            except Exception as e:
                print(f"Warning: Could not load image '{filename}'. Error: {e}")

    if not ref_images:
        print(
            f"Error: No valid reference images found in '{reference_images_dir}' that match the region size."
        )
        return False
    # --- End of pre-loading ---

    start_time = time.monotonic()
    x, y, width, height = region
    print(f"Watching screen region x={x} y={y} w={width} h={height} (timeout={timeout}s)")
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
                print(f"Error comparing images: {e}")

        # Wait before the next check
        time.sleep(interval)

    print(
        f"Timeout: Screen region did not match any reference image within {timeout} seconds."
    )
    if last_capture is not None:
        debug_path = "current_capture.png"
        last_capture.save(debug_path)
        print(f"  Last captured region saved to {debug_path} for inspection.")
    return False
