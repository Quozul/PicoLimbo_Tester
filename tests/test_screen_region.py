"""Tests for :class:`src.infrastructure.screen_region.ScreenRegionMatcher`."""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.infrastructure.screen_region import ScreenRegionMatcher, VALID_EXTENSIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png(path: Path, size: tuple[int, int] = (100, 100),
              color: tuple[int, int, int] = (255, 0, 0)) -> Path:
    """Write a minimal RGB image file and return its path.

    For non-image extensions (e.g. ``.txt``, ``.tiff``), writes raw bytes
    so that ``Image.open`` will fail during loading.
    """
    ext = path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
        img = Image.new("RGB", size, color=color)
        img.save(path)
    else:
        # Write raw bytes so PIL can't identify it as a valid image
        path.write_bytes(b"not an image")
    return path


def _make_mock_image(size: tuple[int, int] = (100, 100)) -> MagicMock:
    """Return a MagicMock that behaves like a converted RGB image."""
    mock = MagicMock()
    mock.size = size
    mock.convert.return_value = mock
    return mock


def _make_diff_mock(has_difference: bool = True) -> MagicMock:
    """Return a MagicMock for ImageChops.difference result."""
    diff = MagicMock()
    if has_difference:
        diff.getbbox.return_value = (0, 0, 1, 1)  # has bounding box → different
    else:
        diff.getbbox.return_value = None  # no bounding box → identical
    return diff


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_defaults(self):
        matcher = ScreenRegionMatcher()
        assert matcher._poll_interval == 0.5
        assert matcher._max_retries == 3

    def test_custom_poll_interval(self):
        matcher = ScreenRegionMatcher(poll_interval=0.1)
        assert matcher._poll_interval == 0.1

    def test_custom_max_retries(self):
        matcher = ScreenRegionMatcher(max_retries=5)
        assert matcher._max_retries == 5

    def test_references_dir_from_path(self, tmp_path):
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        assert matcher._references_dir == tmp_path

    def test_references_dir_from_string(self, tmp_path):
        matcher = ScreenRegionMatcher(references_dir=str(tmp_path))
        assert matcher._references_dir == tmp_path

    def test_default_references_dir(self):
        matcher = ScreenRegionMatcher()
        assert matcher._references_dir == Path("references")


# ---------------------------------------------------------------------------
# 2. Directory validation
# ---------------------------------------------------------------------------

class TestDirectoryValidation:
    def test_returns_false_when_directory_does_not_exist(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        assert matcher.wait_for_region("test", (0, 0, 100, 100), timeout=0.1) is False

    def test_returns_false_when_directory_is_empty(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        matcher = ScreenRegionMatcher(references_dir=empty_dir)
        assert matcher.wait_for_region("test", (0, 0, 100, 100), timeout=0.1) is False


# ---------------------------------------------------------------------------
# 3. Reference image loading
# ---------------------------------------------------------------------------

class TestReferenceLoading:
    def test_loads_png_image(self, tmp_path):
        _make_png(tmp_path / "ref.png", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 1
        assert refs[0][0] == "ref.png"

    def test_loads_jpg_image(self, tmp_path):
        _make_png(tmp_path / "ref.jpg", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 1

    def test_loads_multiple_matching_images(self, tmp_path):
        _make_png(tmp_path / "ref1.png", (100, 100))
        _make_png(tmp_path / "ref2.png", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 2

    def test_skips_unsupported_extensions(self, tmp_path):
        _make_png(tmp_path / "ref.png", (100, 100))
        _make_png(tmp_path / "ref.bmp", (100, 100))
        _make_png(tmp_path / "ref.tiff", (100, 100))
        _make_png(tmp_path / "ref.txt", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 2  # .png and .bmp only

    def test_case_insensitive_extensions(self, tmp_path):
        _make_png(tmp_path / "ref.PNG", (100, 100))
        _make_png(tmp_path / "ref.JPG", (100, 100))
        _make_png(tmp_path / "ref.JpEg", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 3

    def test_all_valid_extensions(self, tmp_path):
        for ext in VALID_EXTENSIONS:
            _make_png(tmp_path / f"ref{ext}", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == len(VALID_EXTENSIONS)

    def test_skips_invalid_image_file(self, tmp_path):
        bad = tmp_path / "bad.png"
        bad.write_text("not an image content")
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 0

    def test_mixed_valid_and_invalid(self, tmp_path):
        _make_png(tmp_path / "good.png", (100, 100))
        bad = tmp_path / "bad.png"
        bad.write_text("not an image")
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 1
        assert refs[0][0] == "good.png"

    def test_skips_images_with_wrong_size(self, tmp_path):
        _make_png(tmp_path / "big.png", (200, 200))
        _make_png(tmp_path / "small.png", (50, 50))
        _make_png(tmp_path / "right.png", (100, 100))
        matcher = ScreenRegionMatcher(references_dir=tmp_path)
        refs = matcher._load_references((100, 100))
        assert len(refs) == 1
        assert refs[0][0] == "right.png"


# ---------------------------------------------------------------------------
# 4. Successful match
# ---------------------------------------------------------------------------

class TestSuccessfulMatch:
    def test_returns_true_on_first_grab(self, tmp_path):
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))

        diff = _make_diff_mock(has_difference=False)  # no difference → match

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=diff),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=[0.0, 0.1]),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            result = matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)
        assert result is True

    def test_matches_second_reference(self, tmp_path):
        """When the first reference doesn't match but the second does."""
        ref1 = _make_mock_image((100, 100))
        ref2 = _make_mock_image((100, 100))

        def _open_side_effect(path, *args, **kwargs):
            filename = os.path.basename(path)
            if filename == "ref1.png":
                ref1.convert.return_value = ref1
                return ref1
            ref2.convert.return_value = ref2
            return ref2

        diff_call = [0]

        def _diff_side_effect(ref, current):
            diff_call[0] += 1
            if diff_call[0] == 1:
                no_match = _make_diff_mock(has_difference=True)
                return no_match
            match = _make_diff_mock(has_difference=False)
            return match

        with (
            patch("src.infrastructure.screen_region.Image.open", side_effect=_open_side_effect),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref2),
            patch("src.infrastructure.screen_region.ImageChops.difference", side_effect=_diff_side_effect),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=[0.0, 0.1]),
        ):
            _make_png(tmp_path / "ref1.png", (100, 100))
            _make_png(tmp_path / "ref2.png", (100, 100))
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            result = matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)
        assert result is True

    def test_matches_on_second_grab(self, tmp_path):
        """First grab doesn't match; second grab matches."""
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))

        diff_call = [0]

        def _diff_side_effect(ref, current):
            diff_call[0] += 1
            if diff_call[0] == 1:
                return _make_diff_mock(has_difference=True)  # no match
            return _make_diff_mock(has_difference=False)  # match

        def _monotonic_side_effect():
            call = diff_call[0]
            if call == 0:
                return 0.0
            if call == 1:
                return 0.1  # first iteration
            return 0.2  # second iteration

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", side_effect=_diff_side_effect),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=_monotonic_side_effect),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path, poll_interval=0.1)
            result = matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)
        assert result is True


# ---------------------------------------------------------------------------
# 5. Timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_returns_false_on_timeout(self, tmp_path):
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))
        no_match = _make_diff_mock(has_difference=True)

        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            return 6.0  # past 5-second timeout

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=no_match),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=_monotonic_side_effect),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            result = matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)
        assert result is False

    def test_checks_multiple_intervals_before_timeout(self, tmp_path):
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))
        no_match = _make_diff_mock(has_difference=True)

        grab_count = [0]

        def _monotonic_side_effect():
            grab_count[0] += 1
            if grab_count[0] <= 3:
                return 0.0
            return 6.0  # past 5-second timeout

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=no_match),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=_monotonic_side_effect),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)
        assert grab_count[0] >= 3


# ---------------------------------------------------------------------------
# 6. Debug image saving
# ---------------------------------------------------------------------------

class TestDebugImageSaving:
    def test_saves_debug_image_on_timeout(self, tmp_path):
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))
        no_match = _make_diff_mock(has_difference=True)

        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            if call_count[0] == 2:
                return 1.0  # enter loop once
            return 6.0  # exit

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=no_match),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=_monotonic_side_effect),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)

        # ref_img is the mock returned by ImageGrab.grab; .save is called on it
        ref_img.save.assert_called_once()

    def test_no_debug_image_when_no_grab_yet(self, tmp_path):
        _make_png(tmp_path / "ref.png", (100, 100))
        ref_img = _make_mock_image((100, 100))

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=[0.0, 6.0]),
            patch("src.infrastructure.screen_region.time.sleep"),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)

        # No save call because timeout fired before first grab
        ref_img.save.assert_not_called()

    def test_no_debug_image_when_no_references(self):
        """No references → no grab → no debug image."""
        with (
            patch("src.infrastructure.screen_region.os.listdir", return_value=[]),
        ):
            matcher = ScreenRegionMatcher(references_dir="/nonexistent")
            matcher.wait_for_region("test", (0, 0, 100, 100), timeout=0.1)
        # No save call because no grab was performed (no valid refs → early return)


# ---------------------------------------------------------------------------
# 7. ValueError handling in ImageChops.difference
# ---------------------------------------------------------------------------

class TestDifferenceErrorHandling:
    def test_handles_value_error_and_continues(self, tmp_path):
        """If ImageChops.difference raises ValueError, skip and continue polling."""
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))

        diff_call = [0]

        def _diff_side_effect(ref, current):
            diff_call[0] += 1
            if diff_call[0] == 1:
                raise ValueError("mode mismatch")
            return _make_diff_mock(has_difference=False)  # match on retry

        def _monotonic_side_effect():
            call = diff_call[0]
            if call == 0:
                return 0.0
            if call == 1:
                return 0.1  # first iteration
            return 0.2  # second iteration

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", side_effect=_diff_side_effect),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=_monotonic_side_effect),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            result = matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)
        assert result is True


# ---------------------------------------------------------------------------
# 8. Region extraction
# ---------------------------------------------------------------------------

class TestRegionExtraction:
    def test_grab_called_with_correct_bbox(self, tmp_path):
        region = (50, 60, 200, 150)
        expected_bbox = (50, 60, 250, 210)
        ref_img = _make_mock_image((200, 150))
        _make_png(tmp_path / "ref.png", (200, 150))
        no_match = _make_diff_mock(has_difference=True)

        call_count = [0]

        def _monotonic_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0
            if call_count[0] == 2:
                return 1.0  # enter loop once
            return 6.0  # exit

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img) as grab_mock,
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=no_match),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=_monotonic_side_effect),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path)
            matcher.wait_for_region("test", region, timeout=5.0)

        grab_mock.assert_called_once_with(bbox=expected_bbox)


# ---------------------------------------------------------------------------
# 9. Poll interval
# ---------------------------------------------------------------------------

class TestPollInterval:
    def test_respects_custom_poll_interval(self, tmp_path):
        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))
        no_match = _make_diff_mock(has_difference=True)

        sleep_calls = []

        def _sleep_side_effect(duration):
            sleep_calls.append(duration)

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=no_match),
            patch("src.infrastructure.screen_region.time.sleep", side_effect=_sleep_side_effect),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=[0.0, 0.15, 6.0]),
        ):
            matcher = ScreenRegionMatcher(references_dir=tmp_path, poll_interval=0.25)
            matcher.wait_for_region("test", (0, 0, 100, 100), timeout=5.0)

        assert all(s == 0.25 for s in sleep_calls)


# ---------------------------------------------------------------------------
# 10. Backwards-compatible wait_for_screen_region function
# ---------------------------------------------------------------------------

class TestBackwardsCompatibleFunction:
    def test_delegates_to_screen_region_matcher(self, tmp_path):
        from src.minecraft.wait_for import wait_for_screen_region

        ref_img = _make_mock_image((100, 100))
        _make_png(tmp_path / "ref.png", (100, 100))
        diff = _make_diff_mock(has_difference=False)

        with (
            patch("src.infrastructure.screen_region.Image.open", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageGrab.grab", return_value=ref_img),
            patch("src.infrastructure.screen_region.ImageChops.difference", return_value=diff),
            patch("src.infrastructure.screen_region.time.sleep"),
            patch("src.infrastructure.screen_region.time.monotonic",
                  side_effect=[0.0, 0.1]),
        ):
            result = wait_for_screen_region(str(tmp_path), (0, 0, 100, 100), timeout=5.0)
        assert result is True
