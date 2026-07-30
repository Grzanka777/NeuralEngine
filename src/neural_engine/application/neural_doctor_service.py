import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from neural_engine.core.paths import RECORD_STORE_NAMES, NeuralHomeError, NeuralPaths
from neural_engine.ports.neural_doctor_probe import (
    NeuralDoctorEvidence,
    NeuralDoctorProbe,
    PathEvidence,
    RecordIssueCode,
    StoreEvidence,
)

MANIFEST_ALGORITHM = "sha256-relative-v1"


class DoctorState(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    label: str
    state: DoctorState
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorStoreResult:
    name: str
    state: DoctorState
    record_count: int
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorManifest:
    state: DoctorState
    algorithm: str
    file_count: int
    aggregate_sha256: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class NeuralDoctorReport:
    source: str
    configured_value: str | None
    resolved_home: str | None
    resolved_brain: str | None
    selection_checks: tuple[DoctorCheck, ...]
    home_checks: tuple[DoctorCheck, ...]
    brain_checks: tuple[DoctorCheck, ...]
    stores: tuple[DoctorStoreResult, ...]
    integrity_checks: tuple[DoctorCheck, ...]
    manifest: DoctorManifest
    ready: bool

    @property
    def failed_check_count(self) -> int:
        checks = (
            *self.selection_checks,
            *self.home_checks,
            *self.brain_checks,
            *self.integrity_checks,
        )
        return (
            sum(check.state == DoctorState.FAIL for check in checks)
            + sum(store.state == DoctorState.FAIL for store in self.stores)
            + (self.manifest.state == DoctorState.FAIL)
        )


class NeuralDoctorService:
    """Derive one bounded read-only operational-readiness report."""

    def __init__(
        self,
        path_resolver: Callable[[], NeuralPaths],
        probe: NeuralDoctorProbe,
        package_version: str,
    ) -> None:
        self._path_resolver = path_resolver
        self._probe = probe
        self._package_version = package_version

    def inspect(self) -> NeuralDoctorReport:
        try:
            paths = self._path_resolver()
        except NeuralHomeError as error:
            return self._unresolved_report(error)

        evidence = self._probe.inspect(paths)
        return self._resolved_report(paths, evidence)

    def _resolved_report(
        self,
        paths: NeuralPaths,
        evidence: NeuralDoctorEvidence,
    ) -> NeuralDoctorReport:
        selection_checks = (
            DoctorCheck("Path resolution", DoctorState.PASS, "selected without fallback"),
        )
        home_checks = self._directory_checks(evidence.home)
        home_ready = self._all_pass(home_checks)
        brain_checks = self._brain_checks(evidence, home_ready)
        brain_path_ready = self._all_pass(brain_checks[:4])
        stores = tuple(self._store_result(store, brain_path_ready) for store in evidence.stores)
        stores_ready = all(store.state == DoctorState.PASS for store in stores)
        integrity_checks = self._integrity_checks(evidence.stores, stores_ready)
        manifest = self._manifest(evidence.stores, stores_ready)
        required_states = (
            *(check.state for check in selection_checks),
            *(check.state for check in home_checks),
            *(check.state for check in brain_checks),
            *(store.state for store in stores),
            *(check.state for check in integrity_checks),
            manifest.state,
        )
        ready = all(state in {DoctorState.PASS, DoctorState.WARN} for state in required_states)

        return NeuralDoctorReport(
            source="override (NEURAL_HOME)" if paths.is_override else "default",
            configured_value=paths.configured_value,
            resolved_home=str(paths.HOME),
            resolved_brain=str(paths.BRAIN),
            selection_checks=selection_checks,
            home_checks=home_checks,
            brain_checks=brain_checks,
            stores=stores,
            integrity_checks=integrity_checks,
            manifest=manifest,
            ready=ready,
        )

    def _brain_checks(
        self,
        evidence: NeuralDoctorEvidence,
        home_ready: bool,
    ) -> tuple[DoctorCheck, ...]:
        if not home_ready:
            skipped = DoctorCheck("Brain prerequisite", DoctorState.SKIP, "home check failed")
            return (skipped, skipped, skipped, skipped, skipped, skipped)

        path_checks = self._directory_checks(evidence.brain)
        brain_ready = self._all_pass(path_checks)
        version = self._version_check(evidence, brain_ready)
        config = self._config_check(evidence.config, brain_ready)
        return (*path_checks, version, config)

    def _version_check(
        self,
        evidence: NeuralDoctorEvidence,
        brain_ready: bool,
    ) -> DoctorCheck:
        if not brain_ready:
            return DoctorCheck("VERSION", DoctorState.SKIP, "Brain check failed")
        path = evidence.version
        if path.inspection_failed:
            return DoctorCheck("VERSION", DoctorState.FAIL, "inspection failed")
        if not path.exists:
            return DoctorCheck("VERSION", DoctorState.FAIL, "missing")
        if not path.is_file:
            return DoctorCheck("VERSION", DoctorState.FAIL, "not a regular file")
        if not path.readable or evidence.version_read_failed:
            return DoctorCheck("VERSION", DoctorState.FAIL, "unreadable")
        if evidence.version_value != self._package_version:
            return DoctorCheck("VERSION", DoctorState.FAIL, "package version mismatch")
        return DoctorCheck("VERSION", DoctorState.PASS, self._package_version)

    @staticmethod
    def _config_check(path: PathEvidence, brain_ready: bool) -> DoctorCheck:
        if not brain_ready:
            return DoctorCheck("config.toml", DoctorState.SKIP, "Brain check failed")
        if path.inspection_failed:
            return DoctorCheck("config.toml", DoctorState.FAIL, "inspection failed")
        if not path.exists:
            return DoctorCheck("config.toml", DoctorState.FAIL, "missing")
        if not path.is_file:
            return DoctorCheck("config.toml", DoctorState.FAIL, "not a regular file")
        if not path.readable:
            return DoctorCheck("config.toml", DoctorState.FAIL, "unreadable")
        return DoctorCheck("config.toml", DoctorState.PASS, "readable")

    @staticmethod
    def _directory_checks(path: PathEvidence) -> tuple[DoctorCheck, ...]:
        if path.inspection_failed:
            failed = DoctorCheck("Exists", DoctorState.FAIL, "inspection failed")
            skipped = DoctorCheck("Dependent check", DoctorState.SKIP, "inspection failed")
            return (failed, skipped, skipped, skipped)
        exists = DoctorCheck(
            "Exists",
            DoctorState.PASS if path.exists else DoctorState.FAIL,
            "yes" if path.exists else "no",
        )
        if not path.exists:
            skipped = DoctorCheck("Dependent check", DoctorState.SKIP, "path is missing")
            return (exists, skipped, skipped, skipped)
        directory = DoctorCheck(
            "Directory",
            DoctorState.PASS if path.is_directory else DoctorState.FAIL,
            "yes" if path.is_directory else "no",
        )
        if not path.is_directory:
            skipped = DoctorCheck("Dependent check", DoctorState.SKIP, "not a directory")
            return (exists, directory, skipped, skipped)
        readable = DoctorCheck(
            "Readable",
            DoctorState.PASS if path.readable else DoctorState.FAIL,
            "yes" if path.readable else "no",
        )
        writable = DoctorCheck(
            "Writable",
            DoctorState.PASS if path.writable else DoctorState.FAIL,
            "yes" if path.writable else "no",
        )
        return (exists, directory, readable, writable)

    @staticmethod
    def _store_result(store: StoreEvidence, brain_ready: bool) -> DoctorStoreResult:
        if not brain_ready:
            return DoctorStoreResult(store.name, DoctorState.SKIP, 0, "Brain check failed")
        path = store.path_evidence
        failures: list[str] = []
        if path.inspection_failed:
            failures.append("inspection failed")
        elif not path.exists:
            failures.append("missing")
        elif not path.is_directory:
            failures.append("not a directory")
        else:
            if not path.readable:
                failures.append("unreadable")
            if not path.writable:
                failures.append("not writable")
        return DoctorStoreResult(
            store.name,
            DoctorState.FAIL if failures else DoctorState.PASS,
            store.record_count,
            ", ".join(failures) if failures else "ready",
        )

    @classmethod
    def _integrity_checks(
        cls,
        stores: tuple[StoreEvidence, ...],
        stores_ready: bool,
    ) -> tuple[DoctorCheck, ...]:
        issues = tuple(issue.code for store in stores for issue in store.issues)
        read_codes: set[RecordIssueCode] = {
            "store_scan_failed",
            "record_not_regular",
            "record_unreadable",
        }
        schema_codes: set[RecordIssueCode] = {
            "invalid_utf8",
            "malformed_json",
            "schema_invalid",
        }
        filename_codes: set[RecordIssueCode] = {"filename_not_uuid"}
        identity_codes: set[RecordIssueCode] = {"identity_mismatch"}
        duplicate_codes: set[RecordIssueCode] = {"duplicate_id"}

        readable = cls._integrity_check(
            "Records readable", issues, read_codes, stores_ready, prerequisite_failed=False
        )
        schema = cls._integrity_check(
            "JSON/domain schema",
            issues,
            schema_codes,
            stores_ready,
            prerequisite_failed=readable.state != DoctorState.PASS,
        )
        filenames = cls._integrity_check(
            "Filename UUIDs",
            issues,
            filename_codes,
            stores_ready,
            prerequisite_failed=schema.state != DoctorState.PASS,
        )
        identity = cls._integrity_check(
            "Filename/payload identity",
            issues,
            identity_codes,
            stores_ready,
            prerequisite_failed=schema.state != DoctorState.PASS,
        )
        duplicates = cls._integrity_check(
            "Per-store unique IDs",
            issues,
            duplicate_codes,
            stores_ready,
            prerequisite_failed=schema.state != DoctorState.PASS,
        )
        return readable, schema, filenames, identity, duplicates

    @staticmethod
    def _integrity_check(
        label: str,
        issues: tuple[RecordIssueCode, ...],
        relevant: set[RecordIssueCode],
        stores_ready: bool,
        *,
        prerequisite_failed: bool,
    ) -> DoctorCheck:
        count = sum(issue in relevant for issue in issues)
        if count:
            return DoctorCheck(label, DoctorState.FAIL, f"{count} failure(s)")
        if not stores_ready or prerequisite_failed:
            return DoctorCheck(label, DoctorState.SKIP, "prerequisite check failed")
        return DoctorCheck(label, DoctorState.PASS, "no failures")

    @staticmethod
    def _manifest(
        stores: tuple[StoreEvidence, ...],
        stores_ready: bool,
    ) -> DoctorManifest:
        entries = tuple(entry for store in stores for entry in store.manifest_entries)
        file_count = sum(store.record_count for store in stores)
        unreadable = any(
            issue.code in {"store_scan_failed", "record_not_regular", "record_unreadable"}
            for store in stores
            for issue in store.issues
        )
        if not stores_ready or unreadable or len(entries) != file_count:
            return DoctorManifest(
                DoctorState.SKIP,
                MANIFEST_ALGORITHM,
                file_count,
                None,
                "complete readable inventory unavailable",
            )
        rows = "".join(
            f"{entry.relative_path}  {entry.content_sha256}\n"
            for entry in sorted(entries, key=lambda item: item.relative_path)
        )
        aggregate = hashlib.sha256(rows.encode("utf-8")).hexdigest()
        return DoctorManifest(
            DoctorState.PASS,
            MANIFEST_ALGORITHM,
            file_count,
            aggregate,
            "complete",
        )

    @staticmethod
    def _all_pass(checks: tuple[DoctorCheck, ...]) -> bool:
        return all(check.state == DoctorState.PASS for check in checks)

    @staticmethod
    def _unresolved_report(error: NeuralHomeError) -> NeuralDoctorReport:
        skipped = DoctorCheck("Prerequisite", DoctorState.SKIP, "path resolution failed")
        stores = tuple(
            DoctorStoreResult(name, DoctorState.SKIP, 0, "path resolution failed")
            for name in RECORD_STORE_NAMES
        )
        resolved_home = str(error.resolved_path) if error.resolved_path is not None else None
        resolved_brain = (
            str(error.resolved_path / "brain") if error.resolved_path is not None else None
        )
        return NeuralDoctorReport(
            source="override (NEURAL_HOME)" if error.source == "override" else "default",
            configured_value=error.configured_value,
            resolved_home=resolved_home,
            resolved_brain=resolved_brain,
            selection_checks=(DoctorCheck("Path resolution", DoctorState.FAIL, str(error)),),
            home_checks=(skipped,),
            brain_checks=(skipped,),
            stores=stores,
            integrity_checks=(skipped,),
            manifest=DoctorManifest(
                DoctorState.SKIP,
                MANIFEST_ALGORITHM,
                0,
                None,
                "path resolution failed",
            ),
            ready=False,
        )
