"""Tests for src/infrastructure/cargo_build.py"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure import cargo_build


class TestCargoBuildAdapter:
    """Tests for the CargoBuildAdapter class."""

    def test_default_timeout(self):
        adapter = cargo_build.CargoBuildAdapter()
        assert adapter._timeout == 1800.0

    def test_default_release_true(self):
        adapter = cargo_build.CargoBuildAdapter()
        assert adapter._release is True

    def test_custom_timeout(self):
        adapter = cargo_build.CargoBuildAdapter(timeout=300.0)
        assert adapter._timeout == 300.0

    def test_release_false(self):
        adapter = cargo_build.CargoBuildAdapter(release=False)
        assert adapter._release is False

    def test_build_raises_when_artifact_missing(self, tmp_path):
        """Build should raise FileNotFoundError when the binary is not found."""
        # Create a minimal Cargo.toml so cargo runs, but do NOT build anything.
        # The adapter will succeed at running cargo (mocked below) but then
        # fail because the expected artifact does not exist.
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "pico_limbo"\nversion = "0.1.0"\nedition = "2021"\n'
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text('fn main() {}')

        with patch("subprocess.run") as mock_run:
            # Simulate a successful cargo build
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            adapter = cargo_build.CargoBuildAdapter()
            with pytest.raises(FileNotFoundError, match="Build artifact not found"):
                adapter.build(tmp_path)

    def test_build_runs_cargo_with_release_flags(self, tmp_path):
        """Build should run cargo build --release by default."""
        # Create a minimal Cargo.toml so cargo doesn't error on missing manifest
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text('fn main() {}')

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # Mock the Path.exists to return True so the artifact check passes
            with patch.object(Path, "exists", return_value=True):
                try:
                    adapter = cargo_build.CargoBuildAdapter()
                    adapter.build(tmp_path)
                except Exception:
                    pass  # We only care that subprocess.run was called correctly

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["cargo", "build", "--release"]
        assert call_args[1]["cwd"] == str(tmp_path)
        assert call_args[1]["timeout"] == 1800.0

    def test_build_runs_cargo_without_release_when_release_false(self, tmp_path):
        """Build should run plain cargo build when release=False."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text('fn main() {}')

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch.object(Path, "exists", return_value=True):
                try:
                    adapter = cargo_build.CargoBuildAdapter(release=False)
                    adapter.build(tmp_path)
                except Exception:
                    pass

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["cargo", "build"]
        assert "--release" not in call_args[0][0]

    def test_build_raises_runtime_error_on_cargo_failure(self, tmp_path):
        """Build should raise RuntimeError when cargo exits non-zero."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text('fn main() {}')

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=101,
                stdout="",
                stderr="error: could not find Cargo.toml",
            )
            with pytest.raises(RuntimeError, match="cargo build failed"):
                adapter = cargo_build.CargoBuildAdapter()
                adapter.build(tmp_path)

    def test_build_returns_path_to_artifact(self, tmp_path):
        """Build should return the path to the built binary."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text('fn main() {}')

        # Create the artifact directory and file so Path.exists works
        artifact_dir = tmp_path / "target" / "release"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = artifact_dir / "pico_limbo"
        artifact_file.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            adapter = cargo_build.CargoBuildAdapter()
            result = adapter.build(tmp_path)

        assert result == artifact_file

    def test_build_uses_custom_timeout(self, tmp_path):
        """Build should use the custom timeout value."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text('fn main() {}')

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch.object(Path, "exists", return_value=True):
                try:
                    adapter = cargo_build.CargoBuildAdapter(timeout=600.0)
                    adapter.build(tmp_path)
                except Exception:
                    pass

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["timeout"] == 600.0


