"""Job aggregate root.

The Job aggregate encapsulates the business logic and invariants
for a single integration test job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.value_objects import (
    ArtifactPath,
    CommitHash,
    ForwardingMethod,
    JobId,
    JobStatus,
    ProxyType,
    RepoUrl,
    TestResult,
    Version,
)


@dataclass
class Job:
    """Job aggregate root.

    Invariants:
    - A job in "building" status cannot have test_results
    - A job in "testing" status must have an artifact_path
    - A job in "finished" or "failed" status cannot be modified
    """

    job_id: JobId
    repo_url: RepoUrl
    ref: str
    commit_hash: CommitHash
    status: JobStatus
    versions: list[Version]
    proxy_type: ProxyType
    forwarding_method: ForwardingMethod
    plugins: list[str] | None
    login_wait_timeout: int
    test_results: dict[str, TestResult] = field(default_factory=dict)
    artifact_path: ArtifactPath | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def transition_to(self, new_status: JobStatus) -> None:
        """Transition the job to a new status, enforcing invariants."""
        # Check if job is in a terminal state
        if self.status in (JobStatus.FINISHED, JobStatus.FAILED):
            raise ValueError(
                f"Job {self.job_id.value} is in terminal state {self.status}"
            )

        # Enforce state machine transitions
        valid_transitions: dict[str, set[str]] = {
            JobStatus.QUEUED: {JobStatus.BUILDING},
            JobStatus.BUILDING: {JobStatus.TESTING, JobStatus.FAILED},
            JobStatus.TESTING: {JobStatus.FINISHED, JobStatus.FAILED},
        }

        if new_status not in valid_transitions.get(self.status, set()):
            raise ValueError(
                f"Invalid transition from {self.status} to {new_status}"
            )

        # Enforce invariants
        if new_status == JobStatus.TESTING and self.artifact_path is None:
            raise ValueError(
                "Job must have an artifact_path to enter testing"
            )
        if new_status == JobStatus.BUILDING and self.test_results:
            raise ValueError(
                "Job cannot have test_results while building"
            )

        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Test result management
    # ------------------------------------------------------------------

    def add_test_result(self, result: TestResult) -> None:
        """Add a test result for a version."""
        if self.status not in (JobStatus.TESTING, JobStatus.FINISHED):
            raise ValueError(
                "Cannot add test results outside of testing/finished state"
            )
        self.test_results[str(result.version)] = result

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for database storage.

        Matches the columns used by src/database.py.
        """
        return {
            "job_id": self.job_id.value,
            "repo_url": self.repo_url.value,
            "ref": self.ref,
            "owner": self._extract_owner(),
            "commit_hash": self.commit_hash.value,
            "status": self.status.value,
            "artifact_path": str(self.artifact_path.value) if self.artifact_path else None,
            "current_step": None,
            "versions": [str(v) for v in self.versions],
            "test_results": {
                k: v.to_dict()
                for k, v in self.test_results.items()
            },
            "error_message": None,
            "eta_seconds": None,
            "proxy": self.proxy_type.value,
            "forwarding_method": self.forwarding_method.value,
            "plugins": self.plugins,
            "login_wait_timeout": self.login_wait_timeout,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def _extract_owner(self) -> str:
        """Extract owner from repo_url using the engine's parser."""
        owner, _ = self.repo_url.parse(self.repo_url.value)
        return owner

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Deserialize from dict (inverse of to_dict)."""
        return cls(
            job_id=JobId(data["job_id"]),
            repo_url=RepoUrl(data["repo_url"]),
            ref=data["ref"],
            commit_hash=CommitHash(data["commit_hash"]),
            status=JobStatus(data["status"]),
            versions=[Version.from_string(v) for v in data["versions"]],
            proxy_type=ProxyType(data["proxy"]),
            forwarding_method=ForwardingMethod(data["forwarding_method"]),
            plugins=data.get("plugins"),
            login_wait_timeout=data.get("login_wait_timeout", 30),
            test_results={
                k: TestResult.from_dict(v, k)
                for k, v in data.get("test_results", {}).items()
            },
            artifact_path=(
                ArtifactPath(Path(data["artifact_path"]))
                if data.get("artifact_path")
                else None
            ),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
