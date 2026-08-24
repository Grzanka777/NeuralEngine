from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.application.brain_trust_inspector import BrainTrustInspector, BrainTrustState
from neural_engine.application.brain_trust_transition import (
    BrainTrustMutationNotPermittedError,
    BrainTrustMutationPreparationError,
    BrainTrustRecoveryExecutionError,
    BrainTrustStalePreimageError,
    BrainTrustTransitionExecutionError,
    BrainTrustUnsafeRecoveryError,
    BrainTrustUnsupportedRecoveryError,
)
from neural_engine.application.evolution_proposal_service import EvolutionProposalService
from neural_engine.core.brain import Brain
from neural_engine.core.brain_trust import (
    BRAIN_TRUST_BINDING_FORMAT,
    BRAIN_TRUST_METADATA_FORMAT,
    BrainMetadata,
    ExternalTrustBinding,
    PendingTransition,
    TargetAction,
    TargetDescriptor,
    TransitionOperationKind,
)
from neural_engine.core.paths import NeuralPaths, resolve_neural_paths
from neural_engine.domain import (
    EvolutionProposal,
    EvolutionProposalStatus,
    Playbook,
    PlaybookEvaluation,
    PlaybookRun,
)
from neural_engine.infrastructure.durability import atomic_replace_bytes
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe
from neural_engine.infrastructure.local_brain_trust_transition import (
    LocalBrainTrustTransitionCoordinator,
    TransitionPersistence,
)
from neural_engine.ports.playbook_evaluation_repository import PlaybookEvaluationRepository
from neural_engine.ports.playbook_repository import PlaybookRepository

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")
TRANSITION_ID = UUID("22222222-2222-4222-8222-222222222222")
PROPOSAL_ID = UUID("33333333-3333-4333-8333-333333333333")
PLAYBOOK_ID = UUID("44444444-4444-4444-8444-444444444444")
EVALUATION_ID = UUID("55555555-5555-4555-8555-555555555555")
RUN_ID = UUID("66666666-6666-4666-8666-666666666666")


@dataclass(frozen=True, slots=True)
class ReplaceFixture:
    paths: NeuralPaths
    binding_path: Path
    repository: JsonEvolutionProposalRepository
    proposal: EvolutionProposal


class EmptyPlaybookRepository(PlaybookRepository):
    def save(self, playbook: Playbook) -> None:
        raise AssertionError("status transition must not save a Playbook")

    def load_all(self) -> list[Playbook]:
        return []

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        return None


class EmptyEvaluationRepository(PlaybookEvaluationRepository):
    def save(self, evaluation: PlaybookEvaluation) -> None:
        raise AssertionError("status transition must not save an Evaluation")

    def load_all(self) -> list[PlaybookEvaluation]:
        return []

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        return None


class EmptyRunReader:
    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        return None


def _proposal(status: EvolutionProposalStatus = EvolutionProposalStatus.DRAFT) -> EvolutionProposal:
    return EvolutionProposal(
        id=PROPOSAL_ID,
        playbook_id=PLAYBOOK_ID,
        evaluation_ids=[EVALUATION_ID],
        summary="Controlled proposal",
        rationale="Status replacement is explicit.",
        proposed_changes=["Protect status replacement"],
        expected_benefits=["No silent overwrite"],
        status=status,
    )


def _fixture(tmp_path: Path, *, trusted: bool = True) -> ReplaceFixture:
    home = tmp_path / "neural-home"
    home.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(home)})
    Brain(paths).initialize()
    binding_path = tmp_path / "binding.json"
    repository = JsonEvolutionProposalRepository(paths=paths)
    proposal = _proposal()
    repository.save(proposal)
    if trusted:
        _write_metadata(paths)
        _write_binding(binding_path)
    return ReplaceFixture(paths, binding_path, repository, proposal)


def _write_metadata(
    paths: NeuralPaths,
    *,
    generation: int = 1,
    pending_transition: PendingTransition | None = None,
) -> BrainMetadata:
    metadata = BrainMetadata(
        metadata_format=BRAIN_TRUST_METADATA_FORMAT,
        brain_id=BRAIN_ID,
        generation=generation,
        pending_transition=pending_transition,
    )
    paths.BRAIN_METADATA.write_bytes(_model_bytes(metadata))
    return metadata


def _write_binding(binding_path: Path, *, generation: int = 1) -> ExternalTrustBinding:
    binding = ExternalTrustBinding(
        binding_format=BRAIN_TRUST_BINDING_FORMAT,
        expected_brain_id=BRAIN_ID,
        accepted_generation=generation,
    )
    binding_path.write_bytes(_model_bytes(binding))
    return binding


def _read_metadata(fixture: ReplaceFixture) -> BrainMetadata:
    return BrainMetadata.model_validate_json(fixture.paths.BRAIN_METADATA.read_bytes())


def _read_binding(fixture: ReplaceFixture) -> ExternalTrustBinding:
    return ExternalTrustBinding.model_validate_json(fixture.binding_path.read_bytes())


def _target_path(fixture: ReplaceFixture) -> Path:
    return fixture.paths.EVOLUTION_PROPOSALS / f"{fixture.proposal.id}.json"


def _inspector(fixture: ReplaceFixture) -> BrainTrustInspector:
    return BrainTrustInspector(
        lambda: fixture.paths,
        LocalBrainTrustProbe(binding_path=fixture.binding_path),
    )


def _coordinator(
    fixture: ReplaceFixture,
    *,
    persistence: TransitionPersistence | None = None,
    post_write_verifier: Callable[[], None] | None = None,
) -> LocalBrainTrustTransitionCoordinator:
    return LocalBrainTrustTransitionCoordinator(
        fixture.paths,
        _inspector(fixture),
        binding_path=fixture.binding_path,
        persistence=persistence,
        transition_id_factory=lambda: TRANSITION_ID,
        post_write_verifier=post_write_verifier,
    )


def _service(
    fixture: ReplaceFixture,
    coordinator: LocalBrainTrustTransitionCoordinator,
) -> EvolutionProposalService:
    return EvolutionProposalService(
        fixture.repository,
        EmptyPlaybookRepository(),
        EmptyEvaluationRepository(),
        EmptyRunReader(),
        controlled_writer=fixture.repository,
        controlled_replace_writer=fixture.repository,
        mutation_coordinator=coordinator,
    )


def _replacement(fixture: ReplaceFixture) -> EvolutionProposal:
    return fixture.proposal.model_copy(update={"status": EvolutionProposalStatus.ACCEPTED})


def _descriptor(fixture: ReplaceFixture, replacement: EvolutionProposal) -> TargetDescriptor:
    path = _target_path(fixture)
    return TargetDescriptor(
        relative_path=path.relative_to(fixture.paths.BRAIN).as_posix(),
        action=TargetAction.REPLACE,
        before_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        after_sha256=hashlib.sha256(
            replacement.model_dump_json(indent=2).encode("utf-8")
        ).hexdigest(),
    )


def _pending(
    descriptor: TargetDescriptor,
    *,
    operation_kind: TransitionOperationKind = TransitionOperationKind.ORDINARY_MUTATION,
    targets: tuple[TargetDescriptor, ...] | None = None,
) -> PendingTransition:
    return PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=1,
        to_generation=2,
        operation_kind=operation_kind,
        targets=targets or (descriptor,),
    )


def _seed_pending(
    fixture: ReplaceFixture,
    transition: PendingTransition,
    *,
    metadata_generation: int = 1,
    binding_generation: int = 1,
) -> None:
    _write_metadata(
        fixture.paths,
        generation=metadata_generation,
        pending_transition=transition,
    )
    _write_binding(fixture.binding_path, generation=binding_generation)


def _model_bytes(model: BrainMetadata | ExternalTrustBinding) -> bytes:
    return model.model_dump_json(indent=2).encode("utf-8")


def _fail_on_call(call_number: int) -> TransitionPersistence:
    calls = 0

    def write_bytes(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == call_number:
            raise OSError(f"injected persistence failure {call_number}")
        atomic_replace_bytes(path, data)

    return TransitionPersistence(write_bytes=write_bytes)


def test_status_uses_one_exact_replace_with_before_after_hashes_and_final_trust(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before_bytes = _target_path(fixture).read_bytes()
    seen_descriptors: list[TargetDescriptor] = []

    def observe_after_metadata() -> None:
        pending = _read_metadata(fixture).pending_transition
        assert pending is not None
        seen_descriptors.append(pending.targets[0])

    updated = _service(
        fixture,
        _coordinator(fixture, post_write_verifier=observe_after_metadata),
    ).set_status(fixture.proposal.id, EvolutionProposalStatus.ACCEPTED)
    after_bytes = _target_path(fixture).read_bytes()

    assert updated.status is EvolutionProposalStatus.ACCEPTED
    assert after_bytes == updated.model_dump_json(indent=2).encode("utf-8")
    assert after_bytes != before_bytes
    assert len(seen_descriptors) == 1
    descriptor = seen_descriptors[0]
    assert descriptor.relative_path == f"evolution-proposals/{fixture.proposal.id}.json"
    assert descriptor.action is TargetAction.REPLACE
    assert descriptor.before_sha256 == hashlib.sha256(before_bytes).hexdigest()
    assert descriptor.after_sha256 == hashlib.sha256(after_bytes).hexdigest()
    assert _read_metadata(fixture).generation == 2
    assert _read_metadata(fixture).pending_transition is None
    assert _read_binding(fixture).accepted_generation == 2
    assert _inspector(fixture).inspect().state is BrainTrustState.TRUSTED_CURRENT


def test_same_status_is_a_protected_noop_without_trust_mutation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    before = _target_path(fixture).read_bytes()

    result = _service(fixture, _coordinator(fixture)).set_status(
        fixture.proposal.id,
        EvolutionProposalStatus.DRAFT,
    )

    assert result == fixture.proposal
    assert _target_path(fixture).read_bytes() == before
    assert _read_metadata(fixture).generation == 1
    assert _read_metadata(fixture).pending_transition is None
    assert _read_binding(fixture).accepted_generation == 1


def test_untrusted_container_composition_rejects_before_replace(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, trusted=False)
    before = _target_path(fixture).read_bytes()

    with pytest.raises(BrainTrustMutationNotPermittedError) as error:
        _service(fixture, _coordinator(fixture)).set_status(
            fixture.proposal.id,
            EvolutionProposalStatus.ACCEPTED,
        )

    assert error.value.state is BrainTrustState.UNADOPTED
    assert _target_path(fixture).read_bytes() == before


def test_stale_preimage_is_rejected_after_marker_without_advancement(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    target_path = _target_path(fixture)
    first_write = True

    def write_bytes(path: Path, data: bytes) -> None:
        nonlocal first_write
        atomic_replace_bytes(path, data)
        if first_write and path == fixture.paths.BRAIN_METADATA:
            first_write = False
            atomic_replace_bytes(target_path, b"external concurrent bytes")

    with pytest.raises(BrainTrustStalePreimageError):
        _service(
            fixture,
            _coordinator(fixture, persistence=TransitionPersistence(write_bytes=write_bytes)),
        ).set_status(fixture.proposal.id, EvolutionProposalStatus.ACCEPTED)

    assert target_path.read_bytes() == b"external concurrent bytes"
    assert _read_metadata(fixture).generation == 1
    assert _read_metadata(fixture).pending_transition is not None
    assert _read_binding(fixture).accepted_generation == 1
    assert _inspector(fixture).inspect().state is BrainTrustState.TRANSITION_PENDING


@pytest.mark.parametrize("payload", [b"not-json", "identity"])
def test_status_rejects_invalid_current_payload_before_marker(
    tmp_path: Path,
    payload: bytes | str,
) -> None:
    fixture = _fixture(tmp_path)
    target_path = _target_path(fixture)
    if payload == "identity":
        invalid = fixture.proposal.model_copy(
            update={"id": UUID("99999999-9999-4999-8999-999999999999")}
        )
        target_path.write_bytes(invalid.model_dump_json(indent=2).encode("utf-8"))
    else:
        assert isinstance(payload, bytes)
        target_path.write_bytes(payload)
    before = target_path.read_bytes()

    with pytest.raises(BrainTrustMutationPreparationError):
        _service(fixture, _coordinator(fixture)).set_status(
            fixture.proposal.id,
            EvolutionProposalStatus.ACCEPTED,
        )

    assert target_path.read_bytes() == before
    assert _read_metadata(fixture).generation == 1
    assert _read_metadata(fixture).pending_transition is None


@pytest.mark.parametrize(
    ("failure", "expected_target", "expected_metadata", "expected_binding", "marker"),
    [
        ("F1", "before", 1, 1, False),
        ("F3", "before", 1, 1, True),
        ("F4", "after", 1, 1, True),
        ("F6", "after", 2, 1, True),
        ("F7", "after", 2, 2, True),
    ],
)
def test_replace_execution_failures_leave_evidence_without_rollback(
    tmp_path: Path,
    failure: str,
    expected_target: str,
    expected_metadata: int,
    expected_binding: int,
    marker: bool,
) -> None:
    fixture = _fixture(tmp_path)
    replacement = _replacement(fixture)
    target_path = _target_path(fixture)
    target = fixture.repository.controlled_replace_target(fixture.proposal, replacement)

    if failure == "F3":

        def fail_publish() -> None:
            raise OSError("injected replacement failure")

        target = target.__class__(
            relative_path=target.relative_path,
            action=target.action,
            after_bytes=target.after_bytes,
            publish=fail_publish,
            before_sha256=target.before_sha256,
        )

    with pytest.raises(BrainTrustTransitionExecutionError):
        _coordinator(
            fixture,
            persistence=_fail_on_call({"F1": 1, "F3": 99, "F4": 2, "F6": 3, "F7": 4}[failure]),
        ).execute(target)

    expected_bytes = (
        fixture.proposal.model_dump_json(indent=2).encode("utf-8")
        if expected_target == "before"
        else replacement.model_dump_json(indent=2).encode("utf-8")
    )
    assert target_path.read_bytes() == expected_bytes
    assert _read_metadata(fixture).generation == expected_metadata
    assert _read_binding(fixture).accepted_generation == expected_binding
    assert (_read_metadata(fixture).pending_transition is not None) is marker


def test_f5_verification_failure_leaves_after_and_pending_marker(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    replacement = _replacement(fixture)
    target = fixture.repository.controlled_replace_target(fixture.proposal, replacement)

    def fail_verification() -> None:
        raise RuntimeError("injected verification failure")

    with pytest.raises(BrainTrustTransitionExecutionError):
        _coordinator(fixture, post_write_verifier=fail_verification).execute(target)

    assert _target_path(fixture).read_bytes() == replacement.model_dump_json(indent=2).encode(
        "utf-8"
    )
    assert _read_metadata(fixture).generation == 2
    assert _read_binding(fixture).accepted_generation == 1
    assert _read_metadata(fixture).pending_transition is not None


@pytest.mark.parametrize(
    ("state", "metadata_generation", "binding_generation"),
    [("R1", 1, 1), ("R2", 1, 1), ("R3", 2, 1), ("R4", 2, 2)],
)
def test_replace_recovery_is_bounded_forward_only(
    tmp_path: Path,
    state: str,
    metadata_generation: int,
    binding_generation: int,
) -> None:
    fixture = _fixture(tmp_path)
    replacement = _replacement(fixture)
    descriptor = _descriptor(fixture, replacement)
    transition = _pending(descriptor)
    _seed_pending(
        fixture,
        transition,
        metadata_generation=metadata_generation,
        binding_generation=binding_generation,
    )
    if state != "R1":
        _target_path(fixture).write_bytes(replacement.model_dump_json(indent=2).encode("utf-8"))
    before = _target_path(fixture).read_bytes()

    if state == "R1":
        with pytest.raises(BrainTrustUnsafeRecoveryError, match="R1_REJECTED"):
            _coordinator(fixture).recover_pending_knowledge_create()
        assert _target_path(fixture).read_bytes() == before
        assert _read_metadata(fixture).generation == 1
        assert _read_binding(fixture).accepted_generation == 1
        assert _read_metadata(fixture).pending_transition == transition
    else:
        assert _coordinator(fixture).recover_pending_knowledge_create() == TRANSITION_ID
        assert _target_path(fixture).read_bytes() == before
        assert _read_metadata(fixture).generation == 2
        assert _read_metadata(fixture).pending_transition is None
        assert _read_binding(fixture).accepted_generation == 2
        assert _inspector(fixture).inspect().state is BrainTrustState.TRUSTED_CURRENT


@pytest.mark.parametrize(
    ("state", "failure_call", "expected_metadata", "expected_binding"),
    [("R2", 1, 1, 1), ("R3", 1, 2, 1), ("R4", 1, 2, 2)],
)
def test_replace_recovery_failures_preserve_pending_forward_state(
    tmp_path: Path,
    state: str,
    failure_call: int,
    expected_metadata: int,
    expected_binding: int,
) -> None:
    fixture = _fixture(tmp_path)
    replacement = _replacement(fixture)
    descriptor = _descriptor(fixture, replacement)
    _seed_pending(
        fixture,
        _pending(descriptor),
        metadata_generation=1 if state == "R2" else 2,
        binding_generation=1 if state != "R4" else 2,
    )
    _target_path(fixture).write_bytes(replacement.model_dump_json(indent=2).encode("utf-8"))

    with pytest.raises(BrainTrustRecoveryExecutionError):
        _coordinator(
            fixture, persistence=_fail_on_call(failure_call)
        ).recover_pending_knowledge_create()

    assert _read_metadata(fixture).generation == expected_metadata
    assert _read_binding(fixture).accepted_generation == expected_binding
    assert _read_metadata(fixture).pending_transition is not None


@pytest.mark.parametrize(
    "case",
    [
        "mismatch",
        "missing",
        "wrong_store",
        "wrong_action",
        "binding_ahead",
        "malformed",
        "identity_mismatch",
        "target_symlink",
        "parent_symlink",
        "generation_outside",
        "multiple_targets",
        "wrong_operation",
    ],
)
def test_replace_recovery_rejects_unsafe_evidence_without_writes(
    tmp_path: Path,
    case: str,
) -> None:
    fixture = _fixture(tmp_path)
    replacement = _replacement(fixture)
    descriptor = _descriptor(fixture, replacement)
    transition = _pending(descriptor)
    target_path = _target_path(fixture)

    if case == "mismatch":
        target_path.write_bytes(b"mismatch")
    elif case == "missing":
        target_path.unlink()
    elif case == "wrong_store":
        descriptor = descriptor.model_copy(
            update={"relative_path": "knowledge/" + target_path.name}
        )
        transition = _pending(descriptor)
    elif case == "wrong_action":
        descriptor = TargetDescriptor(
            relative_path=descriptor.relative_path,
            action=TargetAction.REMOVE,
            before_sha256=descriptor.before_sha256,
        )
        transition = _pending(descriptor)
    elif case == "binding_ahead":
        transition = _pending(descriptor)
    elif case == "malformed":
        target_path.write_bytes(b"not-json")
        descriptor = descriptor.model_copy(
            update={"after_sha256": hashlib.sha256(b"not-json").hexdigest()}
        )
        transition = _pending(descriptor)
    elif case == "identity_mismatch":
        other = replacement.model_copy(update={"id": UUID("77777777-7777-4777-8777-777777777777")})
        target_path.write_bytes(other.model_dump_json(indent=2).encode("utf-8"))
        descriptor = descriptor.model_copy(
            update={"after_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest()}
        )
        transition = _pending(descriptor)
    elif case == "target_symlink":
        outside = tmp_path / "outside.json"
        outside.write_bytes(target_path.read_bytes())
        target_path.unlink()
        target_path.symlink_to(outside)
    elif case == "parent_symlink":
        outside_dir = tmp_path / "outside-proposals"
        outside_dir.mkdir()
        target_path.unlink()
        fixture.paths.EVOLUTION_PROPOSALS.rmdir()
        fixture.paths.EVOLUTION_PROPOSALS.symlink_to(outside_dir, target_is_directory=True)
    elif case == "generation_outside":
        transition = _pending(descriptor)
    elif case == "multiple_targets":
        second = descriptor.model_copy(update={"relative_path": "observations/other.json"})
        transition = _pending(descriptor, targets=(descriptor, second))
    elif case == "wrong_operation":
        transition = _pending(descriptor, operation_kind=TransitionOperationKind.RESTORE)

    _seed_pending(
        fixture,
        transition,
        metadata_generation=3 if case == "generation_outside" else 1,
        binding_generation=2
        if case == "binding_ahead"
        else (3 if case == "generation_outside" else 1),
    )
    before_metadata = fixture.paths.BRAIN_METADATA.read_bytes()
    before_binding = fixture.binding_path.read_bytes()
    before_target = (
        target_path.read_bytes() if target_path.exists() and not target_path.is_symlink() else None
    )

    with pytest.raises(
        (BrainTrustUnsafeRecoveryError, BrainTrustUnsupportedRecoveryError, ValueError)
    ):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert fixture.paths.BRAIN_METADATA.read_bytes() == before_metadata
    assert fixture.binding_path.read_bytes() == before_binding
    if before_target is not None:
        assert target_path.read_bytes() == before_target


def test_replace_recovery_rejects_missing_hashes_without_writes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    replacement = _replacement(fixture)
    descriptor = _descriptor(fixture, replacement)
    transition = _pending(descriptor)
    _seed_pending(fixture, transition)
    raw = json.loads(fixture.paths.BRAIN_METADATA.read_text(encoding="utf-8"))
    raw["pending_transition"]["targets"][0]["before_sha256"] = None
    fixture.paths.BRAIN_METADATA.write_text(json.dumps(raw), encoding="utf-8")
    before_binding = fixture.binding_path.read_bytes()

    with pytest.raises(BrainTrustUnsafeRecoveryError):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert fixture.binding_path.read_bytes() == before_binding


def test_proposal_create_target_remains_create(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    target = fixture.repository.controlled_create_target(
        fixture.proposal.model_copy(update={"id": UUID("88888888-8888-4888-8888-888888888888")})
    )

    assert target.action is TargetAction.CREATE
    assert target.before_sha256 is None
    assert target.after_bytes is not None
