"""Domain value objects for the PicoLimbo Build API.

Pure immutable value objects that enforce invariants at construction time.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from src.versions import Version  # type: ignore[import-untyped]


class JobStatus(str, Enum):
    """Job lifecycle states."""

    QUEUED = "queued"
    BUILDING = "building"
    TESTING = "testing"
    FINISHED = "finished"
    FAILED = "failed"


class ProxyType(str, Enum):
    """Proxy types for server setup."""

    NONE = "none"
    VELOCITY = "velocity"
    BUNGEECORD = "bungeecord"


class ForwardingMethod(str, Enum):
    """Proxy forwarding methods."""

    NONE = "none"
    LEGACY = "legacy"
    BUNGEEGUARD = "bungeeguard"
    MODERN = "modern"


@dataclass(frozen=True)
class JobId:
    """Unique job identifier."""

    value: str

    @classmethod
    def generate(cls) -> JobId:
        """Generate a new random job ID."""
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class RepoUrl:
    """Validated GitHub repository URL."""

    value: str

    @classmethod
    def parse(cls, url: str) -> tuple[str, str]:
        """Extract (owner, repo_name) from a GitHub URL.

        Raises ValueError if the URL is not a valid GitHub repository URL.
        """
        from src.builder.engine import extract_owner_from_url

        return extract_owner_from_url(url)


@dataclass(frozen=True)
class CommitHash:
    """40-character hexadecimal commit hash (validated)."""

    value: str

    def __post_init__(self) -> None:
        if not re.match(r"^[0-9a-fA-F]{40}$", self.value):
            raise ValueError(f"Invalid commit hash: {self.value}")


@dataclass(frozen=True)
class ArtifactPath:
    """Path to a build artifact."""

    value: Path


@dataclass(frozen=True)
class TestResult:
    """Result of testing a single version."""

    __test__ = False  # pyright: ignore[reportGeneralTypeIssues]

    version: Version
    passed: bool
    screenshot_path: Path | None = None
    duration_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for database storage."""
        return {
            "version": str(self.version),
            "passed": self.passed,
            "screenshot_path": str(self.screenshot_path) if self.screenshot_path else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], version_key: str) -> TestResult:
        """Deserialize from a dict.

        Args:
            data: Serialized test result dict.
            version_key: The version string key used in the parent dict.
        """
        return cls(
            version=Version.from_string(data["version"]),
            passed=data["passed"],
            screenshot_path=Path(data["screenshot_path"]) if data.get("screenshot_path") else None,
            duration_seconds=data.get("duration_seconds", 0.0),
            error=data.get("error"),
        )


def is_commit_hash(ref: str) -> bool:
    """Check if a string is a 40-char commit hash."""
    return bool(re.match(r"^[0-9a-fA-F]{40}$", ref))
