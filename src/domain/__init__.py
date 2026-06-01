"""Domain layer for the PicoLimbo Build API.

Exports the main domain types:
- Value objects (JobId, CommitHash, Version, etc.)
- The Job aggregate root
"""

from src.domain.job import Job
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
    is_commit_hash,
)

__all__ = [
    "Job",
    "JobId",
    "JobStatus",
    "ProxyType",
    "ForwardingMethod",
    "RepoUrl",
    "CommitHash",
    "ArtifactPath",
    "TestResult",
    "Version",
    "is_commit_hash",
]
