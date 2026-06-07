"""Unit tests for src/infrastructure/utils.py."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.utils import empty_directory


class TestEmptyDirectory:
    """Tests for empty_directory."""

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Non-existent directory should not raise."""
        nonexistent = str(tmp_path / "does_not_exist")
        empty_directory(nonexistent)  # no exception

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory should not raise."""
        empty_directory(str(tmp_path))  # no exception

    def test_directory_with_files(self, tmp_path: Path) -> None:
        """All files should be removed."""
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        empty_directory(str(tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_directory_with_subdirectories(self, tmp_path: Path) -> None:
        """Subdirectories and their contents should be removed."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")
        (tmp_path / "top.txt").write_text("top")
        empty_directory(str(tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_directory_with_symlinks(self, tmp_path: Path) -> None:
        """Symlinks should be removed (unlinked)."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("real")
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(real_file)
        empty_directory(str(tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_error_logging_on_failure(self, tmp_path: Path) -> None:
        """Errors during deletion are logged, not raised."""
        (tmp_path / "file.txt").write_text("content")

        with patch("os.unlink", side_effect=PermissionError("denied")):
            # Should not raise, just log
            empty_directory(str(tmp_path))

        # File still exists because unlink failed
        assert (tmp_path / "file.txt").exists()
