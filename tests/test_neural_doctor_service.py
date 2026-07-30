import hashlib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from neural_engine.application.neural_doctor_service import (
    MANIFEST_ALGORITHM,
    DoctorState,
    NeuralDoctorService,
)
from neural_engine.core.paths import NeuralHomeError, NeuralPaths, resolve_neural_paths
from neural_engine.ports.neural_doctor_probe import (
    ManifestEntry,
    NeuralDoctorEvidence,
    PathEvidence,
    RecordIssue,
    StoreEvidence,
)


class StaticProbe:
    def __init__(self, evidence: NeuralDoctorEvidence) -> None:
        self.evidence = evidence
        self.inspected: list[NeuralPaths] = []

    def inspect(self, paths: NeuralPaths) -> NeuralDoctorEvidence:
        self.inspected.append(paths)
        return self.evidence


def _path(*, directory: bool = True, writable: bool = True) -> PathEvidence:
    return PathEvidence(
        exists=True,
        is_directory=directory,
        is_file=not directory,
        readable=True,
        writable=writable,
    )


def _evidence(
    paths: NeuralPaths,
    *,
    entries: Mapping[str, tuple[ManifestEntry, ...]] | None = None,
    issues: Mapping[str, tuple[RecordIssue, ...]] | None = None,
    version: str = "1.0.0",
) -> NeuralDoctorEvidence:
    entries = entries or {}
    issues = issues or {}
    return NeuralDoctorEvidence(
        home=_path(),
        brain=_path(),
        version=_path(directory=False),
        version_value=version,
        version_read_failed=False,
        config=_path(directory=False),
        stores=tuple(
            StoreEvidence(
                name=name,
                path=store_path,
                path_evidence=_path(),
                record_count=len(entries.get(name, ())),
                manifest_entries=entries.get(name, ()),
                issues=issues.get(name, ()),
            )
            for name, store_path in paths.record_stores
        ),
    )


def _paths(root: Path) -> NeuralPaths:
    root.mkdir()
    return resolve_neural_paths(environ={"NEURAL_HOME": str(root)})


def test_ready_empty_home_has_empty_manifest_and_all_store_counts(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "portable")
    probe = StaticProbe(_evidence(paths))

    report = NeuralDoctorService(lambda: paths, probe, "1.0.0").inspect()

    assert report.ready
    assert report.source == "override (NEURAL_HOME)"
    assert len(report.stores) == 15
    assert sum(store.record_count for store in report.stores) == 0
    assert report.manifest.algorithm == MANIFEST_ALGORITHM
    assert report.manifest.aggregate_sha256 == hashlib.sha256(b"").hexdigest()
    assert probe.inspected == [paths]


def test_manifest_is_sorted_and_independent_of_selected_mount(tmp_path: Path) -> None:
    first_paths = _paths(tmp_path / "mount-a")
    second_paths = _paths(tmp_path / "mount-b")
    entries = {
        "observations": (
            ManifestEntry("observations/z.json", "2" * 64),
            ManifestEntry("observations/a.json", "1" * 64),
        )
    }
    first = NeuralDoctorService(
        lambda: first_paths, StaticProbe(_evidence(first_paths, entries=entries)), "1.0.0"
    ).inspect()
    second = NeuralDoctorService(
        lambda: second_paths,
        StaticProbe(_evidence(second_paths, entries=entries)),
        "1.0.0",
    ).inspect()
    rows = (f"observations/a.json  {'1' * 64}\nobservations/z.json  {'2' * 64}\n").encode()

    assert first.manifest.aggregate_sha256 == hashlib.sha256(rows).hexdigest()
    assert second.manifest.aggregate_sha256 == first.manifest.aggregate_sha256


def test_version_mismatch_and_record_issues_make_report_not_ready(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path / "portable")
    issues = {
        "observations": (
            RecordIssue("malformed_json", "observations/bad.json"),
            RecordIssue("identity_mismatch", "observations/bad.json"),
            RecordIssue("duplicate_id", "observations/bad.json"),
        )
    }

    report = NeuralDoctorService(
        lambda: paths,
        StaticProbe(_evidence(paths, issues=issues, version="0.9.0")),
        "1.0.0",
    ).inspect()

    assert not report.ready
    assert report.brain_checks[-2].state == DoctorState.FAIL
    assert [check.state for check in report.integrity_checks] == [
        DoctorState.PASS,
        DoctorState.FAIL,
        DoctorState.SKIP,
        DoctorState.FAIL,
        DoctorState.FAIL,
    ]


@pytest.mark.parametrize(
    ("field", "path_evidence", "read_failed", "expected_detail"),
    [
        ("version", PathEvidence(False, False, False, False, False), False, "missing"),
        (
            "version",
            PathEvidence(True, False, True, True, True),
            True,
            "unreadable",
        ),
        (
            "config",
            PathEvidence(True, True, False, True, True),
            False,
            "not a regular file",
        ),
        (
            "config",
            PathEvidence(True, False, True, False, True),
            False,
            "unreadable",
        ),
    ],
)
def test_version_and_config_fail_closed(
    tmp_path: Path,
    field: str,
    path_evidence: PathEvidence,
    read_failed: bool,
    expected_detail: str,
) -> None:
    paths = _paths(tmp_path / "portable")
    evidence = _evidence(paths)
    if field == "version":
        evidence = replace(
            evidence,
            version=path_evidence,
            version_read_failed=read_failed,
        )
    else:
        evidence = replace(evidence, config=path_evidence)

    report = NeuralDoctorService(
        lambda: paths,
        StaticProbe(evidence),
        "1.0.0",
    ).inspect()

    check = report.brain_checks[-2 if field == "version" else -1]
    assert check.state == DoctorState.FAIL
    assert check.detail == expected_detail
    assert not report.ready


def test_unavailable_selection_is_reported_without_probe() -> None:
    def unavailable() -> NeuralPaths:
        raise NeuralHomeError(
            "invalid_configuration",
            source="override",
            configured_value="",
            detail="must not be blank",
        )

    report = NeuralDoctorService(
        unavailable,
        StaticProbe.__new__(StaticProbe),
        "1.0.0",
    ).inspect()

    assert not report.ready
    assert report.selection_checks[0].state == DoctorState.FAIL
    assert all(store.state == DoctorState.SKIP for store in report.stores)
    assert report.manifest.state == DoctorState.SKIP


def test_inaccessible_and_partial_topology_propagate_skip_states(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path / "portable")
    evidence = _evidence(paths)
    first, *remaining = evidence.stores
    unavailable_store = StoreEvidence(
        name=first.name,
        path=first.path,
        path_evidence=PathEvidence(True, True, False, False, False),
        record_count=0,
        manifest_entries=(),
        issues=(),
    )
    partial = NeuralDoctorEvidence(
        home=evidence.home,
        brain=evidence.brain,
        version=evidence.version,
        version_value=evidence.version_value,
        version_read_failed=False,
        config=evidence.config,
        stores=(unavailable_store, *remaining),
    )

    report = NeuralDoctorService(
        lambda: paths,
        StaticProbe(partial),
        "1.0.0",
    ).inspect()

    assert report.stores[0].state == DoctorState.FAIL
    assert all(check.state == DoctorState.SKIP for check in report.integrity_checks)
    assert report.manifest.state == DoctorState.SKIP
    assert not report.ready
