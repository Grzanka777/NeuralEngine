from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from neural_engine.core.paths import NeuralPaths

RecordIssueCode = Literal[
    "store_scan_failed",
    "record_not_regular",
    "record_unreadable",
    "invalid_utf8",
    "malformed_json",
    "schema_invalid",
    "filename_not_uuid",
    "identity_mismatch",
    "duplicate_id",
]


@dataclass(frozen=True, slots=True)
class PathEvidence:
    exists: bool
    is_directory: bool
    is_file: bool
    readable: bool
    writable: bool
    inspection_failed: bool = False


@dataclass(frozen=True, slots=True)
class RecordIssue:
    code: RecordIssueCode
    relative_path: str


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    relative_path: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class StoreEvidence:
    name: str
    path: Path
    path_evidence: PathEvidence
    record_count: int
    manifest_entries: tuple[ManifestEntry, ...]
    issues: tuple[RecordIssue, ...]


@dataclass(frozen=True, slots=True)
class NeuralDoctorEvidence:
    home: PathEvidence
    brain: PathEvidence
    version: PathEvidence
    version_value: str | None
    version_read_failed: bool
    config: PathEvidence
    stores: tuple[StoreEvidence, ...]


class NeuralDoctorProbe(Protocol):
    """Read one selected Neural home without mutating it."""

    def inspect(self, paths: NeuralPaths) -> NeuralDoctorEvidence: ...
