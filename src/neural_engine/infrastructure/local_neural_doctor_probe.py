import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionReview,
    EvolutionProposal,
    Experience,
    Knowledge,
    Observation,
    Playbook,
    PlaybookEvaluation,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionApplication,
    PlaybookRun,
)
from neural_engine.ports.neural_doctor_probe import (
    ManifestEntry,
    NeuralDoctorEvidence,
    PathEvidence,
    RecordIssue,
    StoreEvidence,
)

AccessChecker = Callable[[Path, int], bool]
BytesReader = Callable[[Path], bytes]


class RecordWithId(Protocol):
    id: UUID


_MODEL_BY_STORE: dict[str, type[BaseModel]] = {
    "observations": Observation,
    "experiences": Experience,
    "knowledge": Knowledge,
    "playbooks": Playbook,
    "playbook-runs": PlaybookRun,
    "playbook-evaluations": PlaybookEvaluation,
    "evolution-proposals": EvolutionProposal,
    "playbook-revisions": PlaybookRevision,
    "playbook-revision-activations": PlaybookRevisionActivation,
    "playbook-revision-applications": PlaybookRevisionApplication,
    "decisions": Decision,
    "decision-acceptances": DecisionAcceptance,
    "decision-actions": DecisionAction,
    "decision-outcomes": DecisionOutcome,
    "decision-reviews": DecisionReview,
}


class LocalNeuralDoctorProbe:
    """Inspect local Neural home files without writing to them."""

    def __init__(
        self,
        *,
        access_checker: AccessChecker = os.access,
        bytes_reader: BytesReader | None = None,
    ) -> None:
        self._access_checker = access_checker
        self._bytes_reader = bytes_reader or Path.read_bytes

    def inspect(self, paths: NeuralPaths) -> NeuralDoctorEvidence:
        version = self._path_evidence(paths.VERSION)
        version_value: str | None = None
        version_read_failed = False
        if version.exists and version.is_file and version.readable:
            try:
                version_value = self._bytes_reader(paths.VERSION).decode("utf-8").removesuffix("\n")
            except OSError, UnicodeDecodeError:
                version_read_failed = True

        stores = tuple(self._inspect_store(paths, name, path) for name, path in paths.record_stores)
        return NeuralDoctorEvidence(
            home=self._path_evidence(paths.HOME),
            brain=self._path_evidence(paths.BRAIN),
            version=version,
            version_value=version_value,
            version_read_failed=version_read_failed,
            config=self._path_evidence(paths.CONFIG),
            stores=stores,
        )

    def _inspect_store(
        self,
        paths: NeuralPaths,
        name: str,
        store_path: Path,
    ) -> StoreEvidence:
        path_evidence = self._path_evidence(store_path)
        if (
            path_evidence.inspection_failed
            or not path_evidence.exists
            or not path_evidence.is_directory
            or not path_evidence.readable
        ):
            return StoreEvidence(name, store_path, path_evidence, 0, (), ())

        try:
            candidates = tuple(sorted(store_path.glob("*.json")))
        except OSError:
            issue = RecordIssue("store_scan_failed", name)
            return StoreEvidence(name, store_path, path_evidence, 0, (), (issue,))

        model_type = _MODEL_BY_STORE[name]
        entries: list[ManifestEntry] = []
        issues: list[RecordIssue] = []
        record_ids: set[UUID] = set()
        for path in candidates:
            relative = path.relative_to(paths.BRAIN).as_posix()
            if not path.is_file():
                issues.append(RecordIssue("record_not_regular", relative))
                continue
            if not self._access_checker(path, os.R_OK):
                issues.append(RecordIssue("record_unreadable", relative))
                continue
            try:
                content = self._bytes_reader(path)
            except OSError:
                issues.append(RecordIssue("record_unreadable", relative))
                continue

            entries.append(ManifestEntry(relative, hashlib.sha256(content).hexdigest()))
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(RecordIssue("invalid_utf8", relative))
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                issues.append(RecordIssue("malformed_json", relative))
                continue
            try:
                record = model_type.model_validate(raw)
            except ValidationError:
                issues.append(RecordIssue("schema_invalid", relative))
                continue

            try:
                filename_id = UUID(path.stem)
            except ValueError:
                issues.append(RecordIssue("filename_not_uuid", relative))
                filename_id = None

            record_id = cast(RecordWithId, record).id
            if filename_id is not None and filename_id != record_id:
                issues.append(RecordIssue("identity_mismatch", relative))
            if record_id in record_ids:
                issues.append(RecordIssue("duplicate_id", relative))
            record_ids.add(record_id)

        return StoreEvidence(
            name=name,
            path=store_path,
            path_evidence=path_evidence,
            record_count=len(candidates),
            manifest_entries=tuple(entries),
            issues=tuple(issues),
        )

    def _path_evidence(self, path: Path) -> PathEvidence:
        try:
            exists = path.exists() or path.is_symlink()
            is_directory = exists and path.is_dir()
            is_file = exists and path.is_file()
            read_mode = os.R_OK | (os.X_OK if is_directory else 0)
            write_mode = os.W_OK | (os.X_OK if is_directory else 0)
            return PathEvidence(
                exists=exists,
                is_directory=is_directory,
                is_file=is_file,
                readable=exists and self._access_checker(path, read_mode),
                writable=exists and self._access_checker(path, write_mode),
            )
        except OSError:
            return PathEvidence(False, False, False, False, False, inspection_failed=True)
