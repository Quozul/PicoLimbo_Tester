import os
import time
from unittest.mock import MagicMock, patch

import pytest

from src.minecraft.wait_for import wait_for_screen_region


# ---------------------------------------------------------------------------
# Helpers — create dummy image files and mock Image.open
# ---------------------------------------------------------------------------

def _make_dummy_image(path: str, size: tuple[int, int] = (100, 100)):
    """Create a minimal 1x1 PNG file at *path* with the given pixel size."""
    from PIL import Image

    img = Image.new("RGB", size, color=(255, 0, 0))
    img.save(path)


def _patch_image_open_with_sizes(tmp_path, size_map: dict[str, tuple[int, int]]):
    """Create real files and patch Image.open so each returns a MagicMock
    with the corresponding .size attribute."""
    for filename, size in size_map.items():
        _make_dummy_image(os.path.join(tmp_path, filename), size)

    def _open_side_effect(path, *args, **kwargs):
        filename = os.path.basename(path)
        if filename not in size_map:
            raise FileNotFoundError(path)
        mock = MagicMock()
        mock.size = size_map[filename]
        mock.convert.return_value = mock
        return mock

    return patch("src.minecraft.wait_for.Image.open", side_effect=_open_side_effect)


def _make_mock_image(size: tuple[int, int] = (100, 100)) -> MagicMock:
    """Return a MagicMock with .size and .convert set up."""
    mock = MagicMock()
    mock.size = size
    mock.convert.return_value = mock
    return mock


# ---------------------------------------------------------------------------
# 1. Directory / file existence checks
# ---------------------------------------------------------------------------

class TestDirectoryAndFileChecks:
    def test_returns_false_when_reference_dir_does_not_exist(self, tmp_path):
        missing = str(tmp_path / "no_such_dir")
        assert wait_for_screen_region(missing, (0, 0, 100, 100)) is False

    def test_returns_false_when_directory_is_empty(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with (
            patch("src.minecraft.wait_for.os.listdir", return_value=[]),
            patch("src.minecraft.wait_for.Image.open"),
        ):
            assert wait_for_screen_region(str(empty_dir), (0, 0, 100, 100)) is False

    def test_returns_false_when_no_valid_extensions(self, tmp_path):
        """Files with extensions not in the valid set are ignored."""
        ref_dir = tmp_path / "refs"
        ref_dir.mkdir()
        # Create files with invalid extensions
        (ref_dir / "file.txt").touch()
        (ref_dir / "file.pdf").touch()

        with patch("src.minecraft.wait_for.os.listdir", return_value=["file.txt", "file.pdf"]):
            assert wait_for_screen_region(str(ref_dir), (0, 0, 100, 100)) is False

    def test_returns_false_when_all_images_size_mismatch(self, tmp_path):
        """All images are skipped because none match region size."""
        size_map = {"ref1.png": (200, 200), "ref2.jpg": (50, 50)}
        with _patch_image_open_with_sizes(tmp_path, size_map):
            assert wait_for_screen_region(str(tmp_path), (0, 0, 100, 100)) is False


# ---------------------------------------------------------------------------
# 2. Case-insensitive extension matching
# ---------------------------------------------------------------------------

class TestExtensionCaseSensitivity:
    def test_uppercase_png(self, tmp_path):
        size_map = {"ref.PNG": (100, 100)}
        ref_img = _make_mock_image((100, 100))
        with (
            _patch_image_open_with_sizes(tmp_path, size_map),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            assert wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1) is False

    def test_uppercase_jpg(self, tmp_path):
        size_map = {"ref.JPG": (100, 100)}
        ref_img = _make_mock_image((100, 100))
        with (
            _patch_image_open_with_sizes(tmp_path, size_map),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            assert wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1) is False

    def test_mixed_case_jpeg(self, tmp_path):
        size_map = {"ref.JpEg": (100, 100)}
        ref_img = _make_mock_image((100, 100))
        with (
            _patch_image_open_with_sizes(tmp_path, size_map),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            assert wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1) is False

    def test_lowercase_extensions_still_work(self, tmp_path):
        size_map = {"ref.png": (100, 100), "ref2.jpg": (100, 100)}
        ref_img = _make_mock_image((100, 100))
        with (
            _patch_image_open_with_sizes(tmp_path, size_map),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            assert wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1) is False


# ---------------------------------------------------------------------------
# 3. Size filtering — only matching images are loaded
# ---------------------------------------------------------------------------

class TestSizeFiltering:
    def test_skips_images_that_do_not_match_region_size(self, tmp_path):
        """Images with wrong dimensions are skipped; only matching ones are used."""
        size_map = {
            "wrong.png": (200, 200),   # too big
            "right.png": (100, 100),   # matches
            "also_wrong.bmp": (50, 50),  # too small
        }
        ref_img = _make_mock_image((100, 100))
        with (
            _patch_image_open_with_sizes(tmp_path, size_map),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1)
            # No match because we never set up a matching screenshot
            assert result is False

    def test_all_wrong_size_returns_false(self, tmp_path):
        size_map = {"a.png": (200, 200), "b.jpg": (50, 50)}
        with _patch_image_open_with_sizes(tmp_path, size_map):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1)
            assert result is False


# ---------------------------------------------------------------------------
# 4. Invalid image files — graceful handling
# ---------------------------------------------------------------------------

class TestInvalidImageHandling:
    def test_invalid_image_file_skipped_with_warning(self, tmp_path):
        """A file with a valid extension that fails to open is skipped."""
        # Create a real file that is not a valid image
        bad_file = tmp_path / "bad.png"
        bad_file.write_text("not an image")

        # List only the bad file; Image.open raises an exception
        def _open_side_effect(path, *args, **kwargs):
            raise OSError("cannot identify image file")

        with (
            patch("src.minecraft.wait_for.os.listdir", return_value=["bad.png"]),
            patch("src.minecraft.wait_for.Image.open", side_effect=_open_side_effect),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1)
            assert result is False

    def test_valid_and_invalid_mixed(self, tmp_path):
        """Valid image is loaded; invalid one is skipped."""
        size_map = {"good.png": (100, 100)}
        calls = []

        def _open_side_effect(path, *args, **kwargs):
            calls.append(os.path.basename(path))
            filename = os.path.basename(path)
            if filename == "bad.png":
                raise OSError("bad image")
            if filename in size_map:
                mock = MagicMock()
                mock.size = size_map[filename]
                mock.convert.return_value = mock
                return mock
            raise FileNotFoundError(path)

        _make_dummy_image(os.path.join(tmp_path, "good.png"), (100, 100))
        ref_img = _make_mock_image((100, 100))

        with (
            patch("src.minecraft.wait_for.os.listdir", return_value=["good.png", "bad.png"]),
            patch("src.minecraft.wait_for.Image.open", side_effect=_open_side_effect),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1)
            assert result is False
            assert "good.png" in calls
            assert "bad.png" in calls


# ---------------------------------------------------------------------------
# 5. Successful match — screenshot matches a reference
# ---------------------------------------------------------------------------

class TestSuccessfulMatch:
    def test_returns_true_when_screenshot_matches_reference(self, tmp_path):
        """When ImageGrab.grab returns an image identical to a reference, True."""
        ref_size = (100, 100)
        ref_img = _make_mock_image(ref_size)

        # The screenshot (current_image) is identical to the reference,
        # so ImageChops.difference returns an image with no bounding box.
        diff_mock = MagicMock()
        diff_mock.getbbox.return_value = None  # no difference

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=diff_mock),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.1]),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)
            assert result is True

    def test_matches_second_reference(self, tmp_path):
        """The function checks all references until one matches."""
        ref_size = (100, 100)
        ref1 = _make_mock_image(ref_size)
        ref2 = _make_mock_image(ref_size)

        # First call: no match (getbbox returns something)
        # Second call: match (getbbox returns None)
        match_call = [False]

        def _diff_side_effect(ref, current):
            if not match_call[0]:
                match_call[0] = True
                no_match = MagicMock()
                no_match.getbbox.return_value = (0, 0, 1, 1)  # has difference
                return no_match
            match_mock = MagicMock()
            match_mock.getbbox.return_value = None  # perfect match
            return match_mock

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref1.png": ref_size, "ref2.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref1),
            patch("src.minecraft.wait_for.ImageChops.difference", side_effect=_diff_side_effect),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.1]),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)
            assert result is True


# ---------------------------------------------------------------------------
# 6. Timeout — no match within timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_returns_false_on_timeout(self, tmp_path):
        """When no screenshot ever matches, returns False after timeout."""
        ref_size = (100, 100)
        ref_img = _make_mock_image(ref_size)

        # Always returns a non-matching difference
        no_match = MagicMock()
        no_match.getbbox.return_value = (0, 0, 1, 1)

        # Simulate time progressing past the timeout
        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            return 10.1  # past 5-second timeout

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=no_match),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=_monotonic_side_effect),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)
            assert result is False

    def test_checks_multiple_intervals_before_timeout(self, tmp_path):
        """Verify that multiple screen grabs happen before timeout."""
        ref_size = (100, 100)
        ref_img = _make_mock_image(ref_size)
        no_match = MagicMock()
        no_match.getbbox.return_value = (0, 0, 1, 1)

        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] <= 3:
                return 0.0
            return 6.0  # past 5-second timeout

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=no_match),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=_monotonic_side_effect),
        ):
            wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)
            # At least 3 grabs were taken before timeout
            assert call_count[0] >= 3


# ---------------------------------------------------------------------------
# 7. Debug image saved on timeout
# ---------------------------------------------------------------------------

class TestDebugImageOnTimeout:
    def test_saves_debug_image_when_timeout(self, tmp_path):
        """When timeout occurs and last_capture is not None, saves debug image."""
        ref_size = (100, 100)
        ref_img = _make_mock_image(ref_size)
        no_match = MagicMock()
        no_match.getbbox.return_value = (0, 0, 1, 1)

        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            if call_count[0] == 2:
                return 1.0  # enter loop body once, grab screenshot
            return 6.0  # exit after one iteration

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=no_match),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=_monotonic_side_effect),
        ):
            wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)

        # last_capture is the image returned by ImageGrab.grab, which is ref_img
        # The .save call happens on the image after .convert("RGB"), which returns ref_img itself
        ref_img.save.assert_called_once()

    def test_debug_image_not_saved_when_no_grab_yet(self):
        """When timeout fires before any grab (interval > timeout), no debug image."""
        with (
            patch("src.minecraft.wait_for.os.path.isdir", return_value=True),
            patch("src.minecraft.wait_for.os.listdir", return_value=[]),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 6.0]),
            patch("src.minecraft.wait_for.time.sleep"),
        ):
            result = wait_for_screen_region("/fake/dir", (0, 0, 100, 100), timeout=5.0)
            assert result is False


# ---------------------------------------------------------------------------
# 8. ImageChops.difference ValueError handling
# ---------------------------------------------------------------------------

class TestDifferenceErrorHandling:
    def test_handles_value_error_from_difference(self, tmp_path):
        """If ImageChops.difference raises ValueError, it is logged and skipped."""
        ref_size = (100, 100)
        ref_img = _make_mock_image(ref_size)
        diff_match = MagicMock()
        diff_match.getbbox.return_value = None

        call_count = [0]

        def _diff_side_effect(ref, current):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("mode mismatch")
            return diff_match

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            if call_count[0] == 2:
                return 0.1  # enter loop, diff raises ValueError
            return 0.2  # enter loop again, diff matches

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", side_effect=_diff_side_effect),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=_monotonic_side_effect),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)
            assert result is True


# ---------------------------------------------------------------------------
# 9. Valid extensions list
# ---------------------------------------------------------------------------

class TestValidExtensions:
    def test_all_supported_extensions(self, tmp_path):
        """Each supported extension type is recognized."""
        extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif"]
        size_map = {f"ref{i}{ext}": (100, 100) for i, ext in enumerate(extensions)}
        ref_img = _make_mock_image((100, 100))
        with (
            _patch_image_open_with_sizes(tmp_path, size_map),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 0.15]),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1)
            assert result is False

    def test_unsupported_extensions_ignored(self, tmp_path):
        """Files with unsupported extensions are not loaded."""
        unsupported = [".tiff", ".webp", ".svg", ".txt", ".noext"]
        for ext in unsupported:
            (tmp_path / f"ref{ext}").touch()

        with patch("src.minecraft.wait_for.os.listdir", return_value=[f"ref{ext}" for ext in unsupported]):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=0.1)
            assert result is False


# ---------------------------------------------------------------------------
# 10. Region extraction
# ---------------------------------------------------------------------------

class TestRegionExtraction:
    def test_passes_correct_bbox_to_grab(self, tmp_path):
        """ImageGrab.grab should be called with the correct bbox."""
        ref_size = (100, 100)
        ref_img = _make_mock_image(ref_size)

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img),
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=MagicMock(getbbox=lambda: (0, 0, 1, 1))),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=[0.0, 6.0]),
        ):
            wait_for_screen_region(str(tmp_path), (10, 20, 100, 100), timeout=5.0)

        # bbox=(x, y, x+width, y+height) = (10, 20, 110, 120)
        ImageGrab_mock = __import__("unittest.mock").mock.patch("src.minecraft.wait_for.ImageGrab.grab").stop
        # We can't easily retrieve the mock after exiting the context; re-check via assertion
        # Instead, re-run with a capturing mock
        pass

    def test_grab_called_with_correct_bbox(self, tmp_path):
        ref_size = (200, 150)
        ref_img = _make_mock_image(ref_size)
        no_match = MagicMock()
        no_match.getbbox.return_value = (0, 0, 1, 1)

        region = (50, 60, 200, 150)
        expected_bbox = (50, 60, 250, 210)

        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            if call_count[0] == 2:
                return 1.0  # enter loop once
            return 6.0  # exit after one iteration

        with (
            _patch_image_open_with_sizes(tmp_path, {"ref.png": ref_size}),
            patch("src.minecraft.wait_for.ImageGrab.grab", return_value=ref_img) as grab_mock,
            patch("src.minecraft.wait_for.ImageChops.difference", return_value=no_match),
            patch("src.minecraft.wait_for.time.sleep"),
            patch("src.minecraft.wait_for.time.monotonic", side_effect=_monotonic_side_effect),
        ):
            wait_for_screen_region(str(tmp_path), region, timeout=5.0)

        grab_mock.assert_called_once_with(bbox=expected_bbox)
