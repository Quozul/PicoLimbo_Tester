"""Tests for PaperMCRepository — PaperMC API ACL.

Covers:
- get_latest_mc_version() — fetches latest MC version
- get_download_url() — fetches stable build URL
- download() — downloads file, cleans up on failure
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.infrastructure.papermc_repository import PaperMCRepository


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_http_client():
    """Return a mock httpx.Client for controlled HTTP responses."""
    client = MagicMock(spec=httpx.Client)
    return client


@pytest.fixture
def repo(mock_http_client, tmp_path):
    """Create an PaperMCRepository with a mocked HTTP client."""
    cache = tmp_path / "cache" / "velocity"
    cache.mkdir(parents=True)
    return PaperMCRepository(
        api_base="https://fill.papermc.io/v3/projects/velocity",
        cache_dir=cache,
        http=mock_http_client,
    )


# ============================================================================
# get_latest_mc_version
# ============================================================================


class TestGetLatestMcVersion:
    """Tests for get_latest_mc_version()."""

    def test_returns_latest_version(self, mock_http_client):
        """Returns the first version's id from the API response."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "versions": [
                    {"version": {"id": "1.21.8"}, "builds": [100]},
                    {"version": {"id": "1.20.4"}, "builds": [90]},
                ]
            },
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        result = repo.get_latest_mc_version()

        assert result == "1.21.8"
        mock_http_client.get.assert_called_once_with(
            "https://fill.papermc.io/v3/projects/velocity/versions",
            timeout=30.0,
        )

    def test_empty_versions_raises(self, mock_http_client):
        """Raises RuntimeError when API returns no versions."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"versions": []},
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        with pytest.raises(RuntimeError, match="No Minecraft versions found"):
            repo.get_latest_mc_version()

    def test_http_error_propagates(self, mock_http_client):
        """Raises RuntimeError when the HTTP request fails."""
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            repo.get_latest_mc_version()


# ============================================================================
# get_download_url
# ============================================================================


class TestGetDownloadUrl:
    """Tests for get_download_url()."""

    def test_returns_stable_build_url(self, mock_http_client):
        """Returns the download URL for the latest stable build."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": 343,
                    "channel": "STABLE",
                    "downloads": {
                        "server:default": {
                            "url": "https://cdn.example.com/velocity-343.jar"
                        }
                    },
                },
                {
                    "id": 342,
                    "channel": "BETA",
                    "downloads": {
                        "server:default": {
                            "url": "https://cdn.example.com/velocity-342.jar"
                        }
                    },
                },
            ],
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        result = repo.get_download_url("1.21.8")

        assert result == "https://cdn.example.com/velocity-343.jar"

    def test_returns_none_for_no_stable_build(self, mock_http_client):
        """Returns None when no stable builds exist."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": 342,
                    "channel": "BETA",
                    "downloads": {"server:default": {"url": "https://cdn.example.com/beta.jar"}},
                }
            ],
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        result = repo.get_download_url("1.21.8")

        assert result is None

    def test_returns_none_for_empty_builds_list(self, mock_http_client):
        """Returns None when the builds list is empty."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [],
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        result = repo.get_download_url("1.21.8")

        assert result is None

    def test_returns_none_when_no_server_default(self, mock_http_client):
        """Returns None when downloads server:default is missing."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": 343,
                    "channel": "STABLE",
                    "downloads": {},
                }
            ],
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        result = repo.get_download_url("1.21.8")

        assert result is None

    def test_non_list_response_returns_none(self, mock_http_client):
        """Returns None when the API returns a non-list response."""
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": "bad format"},
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        result = repo.get_download_url("1.21.8")

        assert result is None

    def test_http_error_raises(self, mock_http_client):
        """Raises RuntimeError when the HTTP request fails."""
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=Path("/tmp/cache"),
            http=mock_http_client,
        )
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            repo.get_download_url("1.21.8")


# ============================================================================
# download
# ============================================================================


class TestDownload:
    """Tests for download()."""

    def test_download_succeeds(self, mock_http_client, tmp_path):
        """Successfully downloads and writes file."""
        jar_path = tmp_path / "test.jar"
        mock_http_client.get.return_value = MagicMock(
            status_code=200,
            content=b"fake-jar-content",
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=tmp_path / "cache",
            http=mock_http_client,
        )
        result = repo.download("https://cdn.example.com/velocity.jar", jar_path)

        assert result == jar_path
        assert jar_path.read_bytes() == b"fake-jar-content"

    def test_download_cleans_up_on_failure(self, mock_http_client, tmp_path):
        """Removes partial download file when the request fails."""
        jar_path = tmp_path / "test.jar"
        jar_path.write_bytes(b"partial")

        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=tmp_path / "cache",
            http=mock_http_client,
        )
        with pytest.raises(RuntimeError, match="Failed to download"):
            repo.download("https://cdn.example.com/velocity.jar", jar_path)

        assert not jar_path.exists()

    def test_download_cleans_up_only_existing_file(self, mock_http_client, tmp_path):
        """Does not raise when dest doesn't exist on failure."""
        jar_path = tmp_path / "nonexistent.jar"

        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        repo = PaperMCRepository(
            api_base="https://fill.papermc.io/v3/projects/velocity",
            cache_dir=tmp_path / "cache",
            http=mock_http_client,
        )
        with pytest.raises(RuntimeError, match="Failed to download"):
            repo.download("https://cdn.example.com/velocity.jar", jar_path)


