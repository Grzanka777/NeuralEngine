from pathlib import Path
from uuid import uuid4

from neural_engine.core.brain import Brain
from neural_engine.core.paths import RECORD_STORE_NAMES, NeuralPaths, resolve_neural_paths
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
from neural_engine.infrastructure.local_neural_doctor_probe import (
    _MODEL_BY_STORE,
    LocalNeuralDoctorProbe,
)


def _initialized_paths(root: Path) -> NeuralPaths:
    root.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(root)})
    Brain(paths).initialize()
    return paths


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def test_model_registry_covers_exact_canonical_topology() -> None:
    assert tuple(_MODEL_BY_STORE) == RECORD_STORE_NAMES
    assert tuple(_MODEL_BY_STORE.values()) == (
        Observation,
        Experience,
        Knowledge,
        Playbook,
        PlaybookRun,
        PlaybookEvaluation,
        EvolutionProposal,
        PlaybookRevision,
        PlaybookRevisionActivation,
        PlaybookRevisionApplication,
        Decision,
        DecisionAcceptance,
        DecisionAction,
        DecisionOutcome,
        DecisionReview,
    )


def test_empty_initialized_home_is_inspected_without_writes(tmp_path: Path) -> None:
    paths = _initialized_paths(tmp_path / "portable")
    before = _snapshot(paths.HOME)

    evidence = LocalNeuralDoctorProbe().inspect(paths)

    assert evidence.home.exists and evidence.home.readable and evidence.home.writable
    assert evidence.brain.exists and evidence.brain.readable and evidence.brain.writable
    assert evidence.version_value == "1.0.0"
    assert evidence.config.is_file and evidence.config.readable
    assert len(evidence.stores) == 15
    assert all(store.record_count == 0 for store in evidence.stores)
    assert _snapshot(paths.HOME) == before


def test_record_read_hash_decode_schema_and_identity_are_one_inventory(
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path / "portable")
    record = Observation(content="private payload must not be rendered", tags=["test"])
    record_path = paths.OBSERVATIONS / f"{record.id}.json"
    record_path.write_text(record.model_dump_json(), encoding="utf-8")

    evidence = LocalNeuralDoctorProbe().inspect(paths)
    observations = evidence.stores[0]

    assert observations.record_count == 1
    assert observations.issues == ()
    assert observations.manifest_entries[0].relative_path == (f"observations/{record.id}.json")
    assert len(observations.manifest_entries[0].content_sha256) == 64


def test_corrupt_and_unreadable_records_report_bounded_issue_codes(
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path / "portable")
    malformed = paths.OBSERVATIONS / f"{uuid4()}.json"
    non_utf8 = paths.OBSERVATIONS / f"{uuid4()}.json"
    invalid_schema = paths.OBSERVATIONS / f"{uuid4()}.json"
    unreadable = paths.OBSERVATIONS / f"{uuid4()}.json"
    malformed.write_bytes(b"{")
    non_utf8.write_bytes(b"\xff")
    invalid_schema.write_text("{}", encoding="utf-8")
    unreadable.write_text("secret", encoding="utf-8")

    probe = LocalNeuralDoctorProbe(access_checker=lambda path, _mode: path != unreadable)
    evidence = probe.inspect(paths)
    codes = {issue.code for issue in evidence.stores[0].issues}

    assert codes == {
        "malformed_json",
        "invalid_utf8",
        "schema_invalid",
        "record_unreadable",
    }


def test_filename_payload_mismatch_and_per_store_duplicates_are_detected(
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path / "portable")
    record = Observation(content="same identity")
    for filename_id in (uuid4(), uuid4()):
        (paths.OBSERVATIONS / f"{filename_id}.json").write_text(
            record.model_dump_json(),
            encoding="utf-8",
        )

    evidence = LocalNeuralDoctorProbe().inspect(paths)
    codes = [issue.code for issue in evidence.stores[0].issues]

    assert codes.count("identity_mismatch") == 2
    assert codes.count("duplicate_id") == 1


def test_wrong_type_and_inaccessible_paths_use_deterministic_access_seam(
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path / "portable")
    paths.OBSERVATIONS.rmdir()
    paths.OBSERVATIONS.write_text("wrong type", encoding="utf-8")

    evidence = LocalNeuralDoctorProbe(
        access_checker=lambda path, _mode: path != paths.KNOWLEDGE
    ).inspect(paths)
    stores = {store.name: store for store in evidence.stores}

    assert stores["observations"].path_evidence.is_file
    assert not stores["observations"].path_evidence.is_directory
    assert not stores["knowledge"].path_evidence.readable
