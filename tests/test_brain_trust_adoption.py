from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.application.brain_trust_adoption import (
    AdoptionAuthorizationError,
    AdoptionErrorCode,
    AdoptionManualInterventionError,
    AdoptionNotEligibleError,
    AdoptionState,
    BrainTrustAdoptionError,
)
from neural_engine.application.brain_trust_inspector import BrainTrustInspector
from neural_engine.core.brain import Brain
from neural_engine.core.brain_trust import (
    BRAIN_TRUST_BINDING_FORMAT,
    BRAIN_TRUST_METADATA_FORMAT,
    BrainMetadata,
    ExternalTrustBinding,
    PendingTransition,
    TransitionOperationKind,
)
from neural_engine.core.paths import NeuralPaths, resolve_neural_paths
from neural_engine.domain import Knowledge, KnowledgeConfidence, Observation
from neural_engine.infrastructure.durability import atomic_replace_bytes, create_once_bytes
from neural_engine.infrastructure.local_brain_trust_adoption import (
    AdoptionPersistence,
    LocalBrainTrustAdoptionCoordinator,
)
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")
TRANSITION_ID = UUID("22222222-2222-4222-8222-222222222222")
RECORD_ID = UUID("33333333-3333-4333-8333-333333333333")


@dataclass(frozen=True, slots=True)
class AdoptionFixture:
    paths: NeuralPaths
    backup: Path


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    access_checker: Callable[[Path, int], bool] = os.access,
) -> AdoptionFixture:
    user_home = tmp_path / "user-home"
    neural_home = tmp_path / "neural-home"
    user_home.mkdir()
    neural_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("NEURAL_HOME", str(neural_home))
    paths = resolve_neural_paths(access_checker=access_checker)
    Brain(paths).initialize()
    paths.TRUST_BINDING.parent.mkdir(parents=True)
    backup = tmp_path / "verified-backup.txt"
    backup.write_text("operator-verified backup evidence\n", encoding="utf-8")
    return AdoptionFixture(paths, backup)


def _coordinator(
    fixture: AdoptionFixture,
    *,
    persistence: AdoptionPersistence | None = None,
    brain_id_factory: Callable[[], UUID] = lambda: BRAIN_ID,
    transition_id_factory: Callable[[], UUID] = lambda: TRANSITION_ID,
) -> LocalBrainTrustAdoptionCoordinator:
    inspector = BrainTrustInspector(
        lambda: fixture.paths,
        LocalBrainTrustProbe(),
    )
    return LocalBrainTrustAdoptionCoordinator(
        fixture.paths,
        inspector,
        persistence=persistence,
        brain_id_factory=brain_id_factory,
        transition_id_factory=transition_id_factory,
    )


def _snapshot_records(paths: NeuralPaths) -> tuple[tuple[str, bytes], ...]:
    values: list[tuple[str, bytes]] = []
    for _name, store in paths.record_stores:
        for path in sorted(store.iterdir()):
            values.append((path.relative_to(paths.HOME).as_posix(), path.read_bytes()))
    return tuple(values)


def _metadata(
    fixture: AdoptionFixture,
    *,
    brain_id: UUID = BRAIN_ID,
    pending: PendingTransition | None = None,
) -> BrainMetadata:
    value = BrainMetadata(
        metadata_format=BRAIN_TRUST_METADATA_FORMAT,
        brain_id=brain_id,
        generation=1,
        pending_transition=pending,
    )
    fixture.paths.BRAIN_METADATA.write_bytes(value.model_dump_json(indent=2).encode())
    return value


def _binding(fixture: AdoptionFixture, *, brain_id: UUID = BRAIN_ID) -> ExternalTrustBinding:
    value = ExternalTrustBinding(
        binding_format=BRAIN_TRUST_BINDING_FORMAT,
        expected_brain_id=brain_id,
        accepted_generation=1,
    )
    fixture.paths.TRUST_BINDING.write_bytes(value.model_dump_json(indent=2).encode())
    return value


def _adoption_marker() -> PendingTransition:
    return PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=None,
        to_generation=1,
        operation_kind=TransitionOperationKind.ADOPTION,
        targets=(),
    )


def test_plan_is_read_only_and_requires_explicit_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    coordinator = _coordinator(fixture)
    before = _snapshot_records(fixture.paths)

    plan = coordinator.plan()

    assert plan.state is AdoptionState.UNADOPTED_FRESH
    assert not plan.eligible
    assert any("backup missing" in blocker for blocker in plan.blockers)
    assert fixture.paths.BRAIN_METADATA.exists() is False
    assert fixture.paths.TRUST_BINDING.exists() is False
    assert _snapshot_records(fixture.paths) == before


def test_plan_proves_binding_is_derived_from_home_not_neural_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    plan = _coordinator(fixture).plan(fixture.backup)

    assert plan.eligible
    assert plan.binding_path == (
        tmp_path / "user-home" / ".config/neural-engine" / "brain-trust-binding.json"
    )
    assert plan.binding_path.parent.parent.parent != fixture.paths.HOME


def test_non_writable_neural_home_is_a_preflight_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)

    def deny_home_write(path: Path, mode: int) -> bool:
        if path == fixture.paths.HOME and mode & os.W_OK:
            return False
        return os.access(path, mode)

    blocked_paths = resolve_neural_paths(access_checker=deny_home_write)
    blocked_fixture = AdoptionFixture(blocked_paths, fixture.backup)
    plan = _coordinator(blocked_fixture).plan(fixture.backup)

    assert not plan.eligible
    assert any("home not writable" in blocker for blocker in plan.blockers)
    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()


def test_binding_parent_readiness_is_required_and_never_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    parent = fixture.paths.TRUST_BINDING.parent
    parent.rmdir()

    plan = _coordinator(fixture).plan(fixture.backup)

    assert not plan.eligible
    assert any("binding parent not ready" in blocker for blocker in plan.blockers)
    assert not parent.exists()


def test_symlinked_binding_parent_is_rejected_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    parent = fixture.paths.TRUST_BINDING.parent
    real_parent = tmp_path / "real-binding-parent"
    real_parent.mkdir()
    parent.rmdir()
    parent.symlink_to(real_parent, target_is_directory=True)

    plan = _coordinator(fixture).plan(fixture.backup)

    assert not plan.eligible
    assert any("binding parent not ready" in blocker for blocker in plan.blockers)


def test_cli_confirm_prompts_for_exact_identity_and_executes_synthetic_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    coordinator = _coordinator(fixture)

    class TestContainer:
        def brain_trust_adoption_coordinator(self) -> LocalBrainTrustAdoptionCoordinator:
            return coordinator

    monkeypatch.setattr(cli, "container", TestContainer())
    result = CliRunner().invoke(
        cli.app,
        ["brain", "adopt", "--confirm", "--backup-evidence", str(fixture.backup)],
        input=f"ADOPT {BRAIN_ID}\n",
    )

    assert result.exit_code == 0
    assert "Brain Trust adoption completed" in result.output
    assert "TRUSTED_CURRENT" in result.output
    assert coordinator.classify() is AdoptionState.TRUSTED_CURRENT


def test_successful_empty_adoption_uses_generation_one_and_preserves_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    coordinator = _coordinator(fixture)
    before = _snapshot_records(fixture.paths)

    prepared = coordinator.prepare(fixture.backup)
    result = coordinator.execute(prepared, prepared.confirmation_token)

    metadata = BrainMetadata.model_validate_json(fixture.paths.BRAIN_METADATA.read_bytes())
    binding = ExternalTrustBinding.model_validate_json(fixture.paths.TRUST_BINDING.read_bytes())
    assert result.state is AdoptionState.TRUSTED_CURRENT
    assert result.brain_id == BRAIN_ID
    assert result.generation == 1
    assert metadata.brain_id == binding.expected_brain_id == BRAIN_ID
    assert metadata.generation == binding.accepted_generation == 1
    assert metadata.pending_transition is None
    assert coordinator.classify() is AdoptionState.TRUSTED_CURRENT
    assert _coordinator(fixture).classify() is AdoptionState.TRUSTED_CURRENT
    assert _snapshot_records(fixture.paths) == before


def test_successful_non_empty_adoption_preserves_exact_record_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    observation = Observation(id=RECORD_ID, content="existing record")
    observation_path = fixture.paths.OBSERVATIONS / f"{observation.id}.json"
    observation_path.write_bytes(observation.model_dump_json(indent=2).encode())
    knowledge = Knowledge(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        statement="Existing knowledge",
        rationale="Synthetic adoption fixture",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[],
    )
    knowledge_path = fixture.paths.KNOWLEDGE / f"{knowledge.id}.json"
    knowledge_path.write_bytes(knowledge.model_dump_json(indent=2).encode())
    before = _snapshot_records(fixture.paths)

    coordinator = _coordinator(fixture)
    coordinator.execute(coordinator.prepare(fixture.backup), "ADOPT " + str(BRAIN_ID))

    assert _snapshot_records(fixture.paths) == before
    assert (
        observation_path.read_bytes()
        == dict(before)[observation_path.relative_to(fixture.paths.HOME).as_posix()]
    )
    assert (
        knowledge_path.read_bytes()
        == dict(before)[knowledge_path.relative_to(fixture.paths.HOME).as_posix()]
    )


def test_confirmation_is_identity_bound_and_writes_nothing_when_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    coordinator = _coordinator(fixture)
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(AdoptionAuthorizationError):
        coordinator.execute(prepared, "yes")

    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()


@pytest.mark.parametrize("artifact", ["metadata", "binding"])
def test_preexisting_valid_trust_artifact_blocks_fresh_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact: str,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    if artifact == "metadata":
        _metadata(fixture)
    else:
        _binding(fixture)

    coordinator = _coordinator(fixture)
    plan = coordinator.plan(fixture.backup)

    assert plan.state is AdoptionState.MANUAL_INTERVENTION_REQUIRED
    assert not plan.eligible
    with pytest.raises(AdoptionNotEligibleError):
        coordinator.prepare(fixture.backup)


def test_malformed_trust_artifact_is_manual_intervention_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    fixture.paths.BRAIN_METADATA.write_bytes(b"{")
    before = fixture.paths.BRAIN_METADATA.read_bytes()

    plan = _coordinator(fixture).plan(fixture.backup)

    assert plan.state is AdoptionState.MANUAL_INTERVENTION_REQUIRED
    assert not plan.eligible
    assert fixture.paths.BRAIN_METADATA.read_bytes() == before


@pytest.mark.parametrize(
    ("kind", "build"),
    [
        ("malformed", lambda path: path.write_bytes(b"{")),
        (
            "wrong-filename",
            lambda path: path.with_name("not-a-uuid.json").write_text("{}", encoding="utf-8"),
        ),
        (
            "unsupported-artifact",
            lambda path: path.with_name("unexpected.txt").write_text("x", encoding="utf-8"),
        ),
    ],
)
def test_structural_record_failures_block_before_a1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    build: Callable[[Path], None],
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    build(fixture.paths.OBSERVATIONS / f"{RECORD_ID}.json")

    plan = _coordinator(fixture).plan(fixture.backup)

    assert not plan.eligible, kind
    assert any("record validation failure" in blocker for blocker in plan.blockers)
    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()


def test_symlinked_store_blocks_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    real_store = tmp_path / "real-observations"
    real_store.mkdir()
    fixture.paths.OBSERVATIONS.rmdir()
    fixture.paths.OBSERVATIONS.symlink_to(real_store, target_is_directory=True)

    plan = _coordinator(fixture).plan(fixture.backup)

    assert not plan.eligible
    assert any("unsafe path" in blocker for blocker in plan.blockers)


def test_non_regular_record_blocks_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    (fixture.paths.OBSERVATIONS / "nested").mkdir()

    plan = _coordinator(fixture).plan(fixture.backup)

    assert not plan.eligible
    assert any("regular file" in blocker or "unsafe path" in blocker for blocker in plan.blockers)


def test_wrong_record_identity_blocks_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    observation = Observation(id=RECORD_ID, content="identity mismatch")
    path = fixture.paths.OBSERVATIONS / "55555555-5555-4555-8555-555555555555.json"
    path.write_bytes(observation.model_dump_json().encode())

    plan = _coordinator(fixture).plan(fixture.backup)

    assert not plan.eligible
    assert any("filename/payload identity" in blocker for blocker in plan.blockers)


def test_s1_recovery_creates_binding_then_clears_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    _metadata(fixture, pending=_adoption_marker())
    fixture.paths.BRAIN_METADATA.write_bytes(fixture.paths.BRAIN_METADATA.read_bytes() + b"\n")
    coordinator = _coordinator(fixture)

    result = coordinator.recover("RECOVER ADOPTION")

    assert result.state is AdoptionState.TRUSTED_CURRENT
    assert coordinator.classify() is AdoptionState.TRUSTED_CURRENT
    assert (
        BrainMetadata.model_validate_json(
            fixture.paths.BRAIN_METADATA.read_bytes()
        ).pending_transition
        is None
    )
    assert (
        ExternalTrustBinding.model_validate_json(
            fixture.paths.TRUST_BINDING.read_bytes()
        ).expected_brain_id
        == BRAIN_ID
    )


def test_s2_recovery_preserves_existing_binding_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    _metadata(fixture, pending=_adoption_marker())
    binding = ExternalTrustBinding(
        binding_format=BRAIN_TRUST_BINDING_FORMAT,
        expected_brain_id=BRAIN_ID,
        accepted_generation=1,
    )
    original_binding_bytes = ("{" + binding.model_dump_json()[1:] + "\n").encode()
    fixture.paths.TRUST_BINDING.write_bytes(original_binding_bytes)

    result = _coordinator(fixture).recover("RECOVER ADOPTION")

    assert result.state is AdoptionState.TRUSTED_CURRENT
    assert fixture.paths.TRUST_BINDING.read_bytes() == original_binding_bytes


def test_recovery_requires_exact_authorization_and_does_not_touch_fresh_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    coordinator = _coordinator(fixture)

    with pytest.raises(AdoptionAuthorizationError):
        coordinator.recover("yes")

    assert coordinator.classify() is AdoptionState.UNADOPTED_FRESH
    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()


def test_ordinary_pending_transition_is_not_adoption_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    # The model intentionally rejects empty ordinary target sets, so use an
    # adoption marker with a foreign operation only through raw invalid bytes.
    fixture.paths.BRAIN_METADATA.write_text(
        '{"metadata_format":"1.0.0","brain_id":"11111111-1111-4111-8111-111111111111",'
        '"generation":1,"pending_transition":{"transition_id":"22222222-2222-4222-8222-222222222222",'
        '"brain_id":"11111111-1111-4111-8111-111111111111","from_generation":1,"to_generation":2,'
        '"operation_kind":"ordinary_mutation","targets":[]}}',
        encoding="utf-8",
    )

    assert _coordinator(fixture).classify() is AdoptionState.MANUAL_INTERVENTION_REQUIRED
    with pytest.raises(AdoptionManualInterventionError):
        _coordinator(fixture).recover("RECOVER ADOPTION")


@dataclass
class Faults:
    fail_create_call: int | None = None
    corrupt_create_call: int | None = None
    fail_replace: bool = False
    mutate_records_on_replace: bool = False
    create_calls: int = 0

    def create(self, path: Path, data: bytes) -> None:
        self.create_calls += 1
        if self.fail_create_call == self.create_calls:
            raise OSError("injected create failure")
        create_once_bytes(path, data)
        if self.corrupt_create_call == self.create_calls:
            path.write_bytes(b"corrupted")

    def replace(self, path: Path, data: bytes) -> None:
        if self.mutate_records_on_replace:
            record = self._record_paths[0]
            record.write_bytes(b"changed outside adoption")
        if self.fail_replace:
            raise OSError("injected replace failure")
        atomic_replace_bytes(path, data)

    _record_paths: tuple[Path, ...] = ()


def _fault_persistence(fixture: AdoptionFixture, faults: Faults) -> AdoptionPersistence:
    return AdoptionPersistence(write_bytes=faults.replace, create_once_bytes=faults.create)


def test_f1_and_f2_metadata_publication_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    faults = Faults(fail_create_call=1)
    coordinator = _coordinator(fixture, persistence=_fault_persistence(fixture, faults))
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(BrainTrustAdoptionError) as error:
        coordinator.execute(prepared, prepared.confirmation_token)

    assert error.value.code is AdoptionErrorCode.METADATA_PUBLICATION_FAILURE
    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()


def test_f3_metadata_verification_failure_leaves_marker_without_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    faults = Faults(corrupt_create_call=1)
    coordinator = _coordinator(fixture, persistence=_fault_persistence(fixture, faults))
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(BrainTrustAdoptionError) as error:
        coordinator.execute(prepared, prepared.confirmation_token)

    assert error.value.code is AdoptionErrorCode.METADATA_VERIFICATION_FAILURE
    assert fixture.paths.BRAIN_METADATA.read_bytes() == b"corrupted"
    assert not fixture.paths.TRUST_BINDING.exists()


def test_f4_binding_creation_failure_leaves_s1_recoverable_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    faults = Faults(fail_create_call=2)
    coordinator = _coordinator(fixture, persistence=_fault_persistence(fixture, faults))
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(BrainTrustAdoptionError) as error:
        coordinator.execute(prepared, prepared.confirmation_token)

    assert error.value.code is AdoptionErrorCode.BINDING_CREATION_FAILURE
    assert _coordinator(fixture).classify() is AdoptionState.ADOPTION_PENDING_BINDING
    assert not fixture.paths.TRUST_BINDING.exists()
    assert _coordinator(fixture).recover("RECOVER ADOPTION").state is AdoptionState.TRUSTED_CURRENT


def test_f5_binding_verification_failure_never_overwrites_bad_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    faults = Faults(corrupt_create_call=2)
    coordinator = _coordinator(fixture, persistence=_fault_persistence(fixture, faults))
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(BrainTrustAdoptionError) as error:
        coordinator.execute(prepared, prepared.confirmation_token)

    assert error.value.code is AdoptionErrorCode.BINDING_VERIFICATION_FAILURE
    assert fixture.paths.TRUST_BINDING.read_bytes() == b"corrupted"
    assert _coordinator(fixture).classify() is AdoptionState.MANUAL_INTERVENTION_REQUIRED


def test_f6_marker_clear_failure_leaves_s2_forward_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    faults = Faults(fail_replace=True)
    coordinator = _coordinator(fixture, persistence=_fault_persistence(fixture, faults))
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(BrainTrustAdoptionError) as error:
        coordinator.execute(prepared, prepared.confirmation_token)

    assert error.value.code is AdoptionErrorCode.FINALIZATION_FAILURE
    assert _coordinator(fixture).classify() is AdoptionState.ADOPTION_PENDING_FINALIZATION
    assert _coordinator(fixture).recover("RECOVER ADOPTION").state is AdoptionState.TRUSTED_CURRENT


def test_f7_final_verification_detects_record_drift_after_marker_clear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    observation = Observation(id=RECORD_ID, content="before")
    record_path = fixture.paths.OBSERVATIONS / f"{RECORD_ID}.json"
    record_path.write_bytes(observation.model_dump_json().encode())
    faults = Faults(mutate_records_on_replace=True, _record_paths=(record_path,))
    coordinator = _coordinator(fixture, persistence=_fault_persistence(fixture, faults))
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(AdoptionManualInterventionError):
        coordinator.execute(prepared, prepared.confirmation_token)

    assert (
        BrainMetadata.model_validate_json(
            fixture.paths.BRAIN_METADATA.read_bytes()
        ).pending_transition
        is None
    )
    assert _coordinator(fixture).classify() is AdoptionState.TRUSTED_CURRENT


def test_f8_record_drift_between_a1_and_a2_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    observation = Observation(id=RECORD_ID, content="before")
    record_path = fixture.paths.OBSERVATIONS / f"{RECORD_ID}.json"
    record_path.write_bytes(observation.model_dump_json().encode())
    original_create = create_once_bytes
    calls = 0

    def drift_after_a1(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        original_create(path, data)
        if calls == 1:
            record_path.write_bytes(b"drift")

    persistence = AdoptionPersistence(create_once_bytes=drift_after_a1)
    coordinator = _coordinator(fixture, persistence=persistence)
    prepared = coordinator.prepare(fixture.backup)

    with pytest.raises(AdoptionManualInterventionError):
        coordinator.execute(prepared, prepared.confirmation_token)

    assert not fixture.paths.TRUST_BINDING.exists()


def test_cli_plan_is_read_only_and_reports_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    before = _snapshot_records(fixture.paths)

    result = CliRunner().invoke(
        cli.app,
        [
            "brain",
            "adopt",
            "--plan",
            "--backup-evidence",
            str(fixture.backup),
        ],
    )

    assert result.exit_code == 0
    assert "Brain Trust adoption plan" in result.output
    assert "UNADOPTED_FRESH" in result.output
    assert "Eligible          : yes" in result.output
    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()
    assert _snapshot_records(fixture.paths) == before


def test_cli_confirm_rejects_generic_confirmation_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        cli.app,
        [
            "brain",
            "adopt",
            "--confirm",
            "--backup-evidence",
            str(fixture.backup),
            "--confirmation",
            "yes",
        ],
    )

    assert result.exit_code == 1
    assert "authorization rejected" in result.output
    assert not fixture.paths.BRAIN_METADATA.exists()
    assert not fixture.paths.TRUST_BINDING.exists()


def test_ordinary_brain_recover_does_not_recover_adoption_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    _metadata(fixture, pending=_adoption_marker())

    result = CliRunner().invoke(cli.app, ["brain", "recover"])

    assert result.exit_code == 1
    assert "recovered" not in result.output
    assert (
        BrainMetadata.model_validate_json(
            fixture.paths.BRAIN_METADATA.read_bytes()
        ).pending_transition
        is not None
    )
