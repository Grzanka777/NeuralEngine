from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.application.brain_trust_inspector import (
    BrainTrustInspector,
    BrainTrustState,
)
from neural_engine.application.brain_trust_transition import (
    BrainTrustMutationNotPermittedError,
    BrainTrustNoRecoverableTransitionError,
    BrainTrustRecoveryExecutionError,
    BrainTrustTransitionExecutionError,
    BrainTrustUnsafeRecoveryError,
    BrainTrustUnsupportedRecoveryError,
)
from neural_engine.application.knowledge_service import KnowledgeService
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
from neural_engine.domain import Experience, ExperienceResult, Knowledge, KnowledgeConfidence
from neural_engine.infrastructure.durability import atomic_replace_bytes
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe
from neural_engine.infrastructure.local_brain_trust_transition import (
    LocalBrainTrustTransitionCoordinator,
    TransitionPersistence,
)
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")
FOREIGN_BRAIN_ID = UUID("22222222-2222-4222-8222-222222222222")
EXPERIENCE_ID = UUID("33333333-3333-4333-8333-333333333333")


@dataclass(frozen=True, slots=True)
class TrustFixture:
    paths: NeuralPaths
    binding_path: Path


class StaticExperienceReader:
    def __init__(self, experience: Experience) -> None:
        self._experience = experience

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        if experience_id == self._experience.id:
            return self._experience
        return None


def _fixture(tmp_path: Path) -> TrustFixture:
    home = tmp_path / "neural-home"
    home.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(home)})
    Brain(paths).initialize()
    binding_path = tmp_path / "binding.json"
    return TrustFixture(paths, binding_path)


def _metadata(
    fixture: TrustFixture,
    *,
    brain_id: UUID = BRAIN_ID,
    generation: int = 1,
    pending_transition: PendingTransition | None = None,
) -> BrainMetadata:
    value = BrainMetadata(
        metadata_format=BRAIN_TRUST_METADATA_FORMAT,
        brain_id=brain_id,
        generation=generation,
        pending_transition=pending_transition,
    )
    fixture.paths.BRAIN_METADATA.write_bytes(value.model_dump_json(indent=2).encode("utf-8"))
    return value


def _binding(
    fixture: TrustFixture,
    *,
    brain_id: UUID = BRAIN_ID,
    generation: int = 1,
) -> ExternalTrustBinding:
    value = ExternalTrustBinding(
        binding_format=BRAIN_TRUST_BINDING_FORMAT,
        expected_brain_id=brain_id,
        accepted_generation=generation,
    )
    fixture.binding_path.write_bytes(value.model_dump_json(indent=2).encode("utf-8"))
    return value


def _trusted_fixture(tmp_path: Path) -> TrustFixture:
    fixture = _fixture(tmp_path)
    _metadata(fixture)
    _binding(fixture)
    return fixture


def _inspector(fixture: TrustFixture) -> BrainTrustInspector:
    return BrainTrustInspector(
        lambda: fixture.paths,
        LocalBrainTrustProbe(binding_path=fixture.binding_path),
    )


def _coordinator(
    fixture: TrustFixture,
    *,
    persistence: TransitionPersistence | None = None,
    post_write_verifier: Callable[[], None] | None = None,
) -> LocalBrainTrustTransitionCoordinator:
    return LocalBrainTrustTransitionCoordinator(
        fixture.paths,
        _inspector(fixture),
        binding_path=fixture.binding_path,
        persistence=persistence,
        transition_id_factory=lambda: UUID("44444444-4444-4444-8444-444444444444"),
        post_write_verifier=post_write_verifier,
    )


def _knowledge() -> Knowledge:
    return Knowledge(
        id=UUID("55555555-5555-4555-8555-555555555555"),
        statement="Controlled knowledge",
        rationale="The transition is observable.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[EXPERIENCE_ID],
    )


def _target(
    fixture: TrustFixture,
) -> tuple[JsonKnowledgeRepository, Knowledge, ControlledMutationTarget]:
    repository = JsonKnowledgeRepository(paths=fixture.paths)
    knowledge = _knowledge()
    return repository, knowledge, repository.controlled_create_target(knowledge)


def _read_metadata(fixture: TrustFixture) -> BrainMetadata:
    return BrainMetadata.model_validate_json(fixture.paths.BRAIN_METADATA.read_bytes())


def _read_binding(fixture: TrustFixture) -> ExternalTrustBinding:
    return ExternalTrustBinding.model_validate_json(fixture.binding_path.read_bytes())


def _target_path(fixture: TrustFixture, knowledge: Knowledge) -> Path:
    return fixture.paths.KNOWLEDGE / f"{knowledge.id}.json"


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _assert_pending_marker(fixture: TrustFixture, target: ControlledMutationTarget) -> None:
    marker = _read_metadata(fixture).pending_transition
    assert marker is not None
    assert marker.from_generation == 1
    assert marker.to_generation == 2
    assert marker.operation_kind is TransitionOperationKind.ORDINARY_MUTATION
    assert marker.targets[0].relative_path == target.relative_path
    assert marker.targets[0].before_sha256 is None
    assert marker.targets[0].after_sha256 == hashlib.sha256(target.after_bytes or b"").hexdigest()


def test_knowledge_add_uses_controlled_transition_and_clears_marker_last(
    tmp_path: Path,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    before_files = _file_snapshot(fixture.paths.HOME)
    before_binding = fixture.binding_path.read_bytes()
    repository = JsonKnowledgeRepository(paths=fixture.paths)
    experience = Experience(
        id=EXPERIENCE_ID,
        title="Evidence",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.SUCCESS,
    )
    writes: list[Path] = []

    def write_bytes(path: Path, data: bytes) -> None:
        writes.append(path)
        atomic_replace_bytes(path, data)

    seen_descriptor: list[TargetDescriptor] = []

    def inspect_pending_marker() -> None:
        marker = _read_metadata(fixture).pending_transition
        assert marker is not None
        seen_descriptor.extend(marker.targets)

    coordinator = _coordinator(
        fixture,
        persistence=TransitionPersistence(write_bytes=write_bytes),
        post_write_verifier=inspect_pending_marker,
    )
    service = KnowledgeService(
        repository,
        StaticExperienceReader(experience),
        controlled_writer=repository,
        mutation_coordinator=coordinator,
    )

    knowledge = service.add(
        statement="Controlled knowledge",
        rationale="The transition is observable.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[EXPERIENCE_ID],
    )

    target_path = _target_path(fixture, knowledge)
    assert target_path.read_bytes() == knowledge.model_dump_json(indent=2).encode("utf-8")
    assert _read_metadata(fixture).generation == 2
    assert _read_metadata(fixture).pending_transition is None
    assert _read_binding(fixture).accepted_generation == 2
    assert _inspector(fixture).inspect().state is BrainTrustState.TRUSTED_CURRENT
    assert writes == [
        fixture.paths.BRAIN_METADATA,
        fixture.paths.BRAIN_METADATA,
        fixture.binding_path,
        fixture.paths.BRAIN_METADATA,
    ]
    assert len(seen_descriptor) == 1
    descriptor = seen_descriptor[0]
    assert descriptor.action is TargetAction.CREATE
    assert descriptor.before_sha256 is None
    assert descriptor.after_sha256 == hashlib.sha256(target_path.read_bytes()).hexdigest()

    after_files = _file_snapshot(fixture.paths.HOME)
    expected_changed_files = {
        fixture.paths.BRAIN_METADATA.relative_to(fixture.paths.HOME).as_posix(),
        target_path.relative_to(fixture.paths.HOME).as_posix(),
    }
    assert set(after_files) <= set(before_files) | expected_changed_files
    for relative_path, before_bytes in before_files.items():
        if relative_path not in expected_changed_files:
            assert after_files[relative_path] == before_bytes
    assert fixture.binding_path.read_bytes() != before_binding


@pytest.mark.parametrize(
    "state",
    [
        BrainTrustState.UNADOPTED,
        BrainTrustState.TRANSITION_PENDING,
        BrainTrustState.FOREIGN,
        BrainTrustState.STALE_OR_ROLLBACK,
        BrainTrustState.UNTRUSTED_AHEAD,
        BrainTrustState.BINDING_MISSING,
        BrainTrustState.METADATA_INVALID,
        BrainTrustState.RECOVERY_REQUIRED,
    ],
)
def test_controlled_mutation_rejects_every_ineligible_trust_state(
    tmp_path: Path,
    state: BrainTrustState,
) -> None:
    fixture = _fixture(tmp_path)
    if state is BrainTrustState.UNADOPTED:
        pass
    elif state is BrainTrustState.TRANSITION_PENDING:
        marker = PendingTransition(
            transition_id=UUID("66666666-6666-4666-8666-666666666666"),
            brain_id=BRAIN_ID,
            from_generation=1,
            to_generation=2,
            operation_kind=TransitionOperationKind.ORDINARY_MUTATION,
            targets=(
                TargetDescriptor(
                    relative_path="knowledge/other.json",
                    action=TargetAction.CREATE,
                    after_sha256="a" * 64,
                ),
            ),
        )
        _metadata(fixture, pending_transition=marker)
        _binding(fixture)
    elif state is BrainTrustState.FOREIGN:
        _metadata(fixture)
        _binding(fixture, brain_id=FOREIGN_BRAIN_ID, generation=1)
    elif state is BrainTrustState.STALE_OR_ROLLBACK:
        _metadata(fixture, generation=1)
        _binding(fixture, generation=2)
    elif state is BrainTrustState.UNTRUSTED_AHEAD:
        _metadata(fixture, generation=2)
        _binding(fixture, generation=1)
    elif state is BrainTrustState.BINDING_MISSING:
        _metadata(fixture)
    elif state is BrainTrustState.METADATA_INVALID:
        fixture.paths.BRAIN_METADATA.write_bytes(b"{")
        _binding(fixture)
    elif state is BrainTrustState.RECOVERY_REQUIRED:
        _metadata(fixture)
        fixture.binding_path.write_bytes(b"{")

    repository, knowledge, target = _target(fixture)
    coordinator = _coordinator(fixture)

    assert _inspector(fixture).inspect().state is state
    with pytest.raises(BrainTrustMutationNotPermittedError) as error:
        coordinator.execute(target)

    assert error.value.state is state
    assert not _target_path(fixture, knowledge).exists()
    assert repository.get_by_id(knowledge.id) is None


def _fail_on_call(call_number: int) -> TransitionPersistence:
    calls = 0

    def write_bytes(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == call_number:
            raise OSError(f"injected persistence failure {call_number}")
        atomic_replace_bytes(path, data)

    return TransitionPersistence(write_bytes=write_bytes)


@pytest.mark.parametrize(
    ("failure", "metadata_generation", "binding_generation", "target_exists", "marker"),
    [
        ("F1", 1, 1, False, False),
        ("F3", 1, 1, True, True),
        ("F5", 2, 1, True, True),
        ("F6", 2, 2, True, True),
    ],
)
def test_persistence_failures_leave_exact_durable_evidence(
    tmp_path: Path,
    failure: str,
    metadata_generation: int,
    binding_generation: int,
    target_exists: bool,
    marker: bool,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    call_number = {"F1": 1, "F3": 2, "F5": 3, "F6": 4}[failure]

    with pytest.raises(BrainTrustTransitionExecutionError):
        _coordinator(fixture, persistence=_fail_on_call(call_number)).execute(target)

    target_path = _target_path(fixture, knowledge)
    assert target_path.exists() is target_exists
    assert _read_metadata(fixture).generation == metadata_generation
    assert _read_binding(fixture).accepted_generation == binding_generation
    assert (_read_metadata(fixture).pending_transition is not None) is marker
    if marker:
        _assert_pending_marker(fixture, target)


def test_f2_target_failure_leaves_pending_marker_and_binding_unchanged(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, original_target = _target(fixture)

    def fail_target() -> None:
        raise OSError("injected target failure")

    target = ControlledMutationTarget(
        relative_path=original_target.relative_path,
        action=original_target.action,
        after_bytes=original_target.after_bytes,
        publish=fail_target,
    )

    with pytest.raises(BrainTrustTransitionExecutionError):
        _coordinator(fixture).execute(target)

    assert not _target_path(fixture, knowledge).exists()
    assert _read_metadata(fixture).generation == 1
    assert _read_binding(fixture).accepted_generation == 1
    _assert_pending_marker(fixture, target)


def test_f4_verification_failure_leaves_new_target_and_pending_marker(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)

    def fail_verification() -> None:
        raise RuntimeError("injected verification failure")

    with pytest.raises(BrainTrustTransitionExecutionError):
        _coordinator(fixture, post_write_verifier=fail_verification).execute(target)

    assert _target_path(fixture, knowledge).read_bytes() == target.after_bytes
    assert _read_metadata(fixture).generation == 2
    assert _read_binding(fixture).accepted_generation == 1
    _assert_pending_marker(fixture, target)


def test_pending_transition_blocks_a_later_mutation_attempt(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, original_knowledge, target = _target(fixture)

    with pytest.raises(BrainTrustTransitionExecutionError):
        _coordinator(fixture, persistence=_fail_on_call(3)).execute(target)

    next_repository = JsonKnowledgeRepository(paths=fixture.paths)
    next_knowledge = original_knowledge.model_copy(
        update={"id": UUID("77777777-7777-4777-8777-777777777777")}
    )
    next_target = next_repository.controlled_create_target(next_knowledge)
    with pytest.raises(BrainTrustMutationNotPermittedError) as error:
        _coordinator(fixture).execute(next_target)

    assert error.value.state is BrainTrustState.TRANSITION_PENDING
    assert not _target_path(fixture, next_knowledge).exists()


def _recovery_transition(
    target: ControlledMutationTarget,
    *,
    operation_kind: TransitionOperationKind = TransitionOperationKind.ORDINARY_MUTATION,
    targets: tuple[TargetDescriptor, ...] | None = None,
    brain_id: UUID = BRAIN_ID,
    from_generation: int = 1,
    to_generation: int = 2,
) -> PendingTransition:
    descriptor = TargetDescriptor(
        relative_path=target.relative_path,
        action=target.action,
        after_sha256=hashlib.sha256(target.after_bytes or b"").hexdigest(),
    )
    return PendingTransition(
        transition_id=UUID("88888888-8888-4888-8888-888888888888"),
        brain_id=brain_id,
        from_generation=from_generation,
        to_generation=to_generation,
        operation_kind=operation_kind,
        targets=targets or (descriptor,),
    )


def _seed_recovery_state(
    fixture: TrustFixture,
    target: ControlledMutationTarget,
    *,
    metadata_generation: int = 1,
    binding_generation: int = 1,
    target_exists: bool = True,
    transition: PendingTransition | None = None,
    binding_brain_id: UUID = BRAIN_ID,
) -> PendingTransition:
    if target_exists:
        target.publish()
    marker = transition or _recovery_transition(target)
    _metadata(fixture, generation=metadata_generation, pending_transition=marker)
    _binding(fixture, brain_id=binding_brain_id, generation=binding_generation)
    return marker


def _recovery_snapshot(fixture: TrustFixture) -> tuple[dict[str, bytes], bytes | None]:
    binding = fixture.binding_path.read_bytes() if fixture.binding_path.exists() else None
    return _file_snapshot(fixture.paths.HOME), binding


def _replace_target_with_symlink(target_path: Path, destination: Path) -> None:
    target_path.unlink()
    target_path.symlink_to(destination)


def test_recovery_rejects_s1_without_any_write(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, _knowledge, target = _target(fixture)
    _seed_recovery_state(fixture, target, target_exists=False)
    before = _recovery_snapshot(fixture)

    with pytest.raises(BrainTrustUnsafeRecoveryError, match="S1_REJECTED_INSUFFICIENT_EVIDENCE"):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _recovery_snapshot(fixture) == before


def test_recovery_rejects_internal_target_symlink_without_any_write(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    _seed_recovery_state(fixture, target)
    target_path = _target_path(fixture, knowledge)
    alias_path = fixture.paths.KNOWLEDGE / "alias.json"
    alias_path.write_bytes(target.after_bytes or b"")
    _replace_target_with_symlink(target_path, alias_path)
    before = _recovery_snapshot(fixture)

    with pytest.raises(BrainTrustUnsafeRecoveryError, match="symbolic link"):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _recovery_snapshot(fixture) == before
    assert target_path.is_symlink()
    assert target_path.readlink() == alias_path
    assert alias_path.read_bytes() == target.after_bytes


def test_recovery_rejects_outside_target_symlink_without_any_write(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    _seed_recovery_state(fixture, target)
    target_path = _target_path(fixture, knowledge)
    outside_path = tmp_path / "outside.json"
    outside_path.write_bytes(target.after_bytes or b"")
    _replace_target_with_symlink(target_path, outside_path)
    before = _recovery_snapshot(fixture)
    outside_before = outside_path.read_bytes()

    with pytest.raises(BrainTrustUnsafeRecoveryError, match="symbolic link"):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _recovery_snapshot(fixture) == before
    assert target_path.is_symlink()
    assert target_path.readlink() == outside_path
    assert outside_path.read_bytes() == outside_before


def test_recovery_rejects_symlinked_knowledge_parent_without_any_write(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    _seed_recovery_state(fixture, target)
    target_path = _target_path(fixture, knowledge)
    real_knowledge_path = fixture.paths.BRAIN / "knowledge-real"
    fixture.paths.KNOWLEDGE.rename(real_knowledge_path)
    fixture.paths.KNOWLEDGE.symlink_to(real_knowledge_path, target_is_directory=True)
    before = _recovery_snapshot(fixture)

    with pytest.raises(BrainTrustUnsafeRecoveryError, match="symbolic link"):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _recovery_snapshot(fixture) == before
    assert fixture.paths.KNOWLEDGE.is_symlink()
    assert fixture.paths.KNOWLEDGE.readlink() == real_knowledge_path
    assert target_path.read_bytes() == target.after_bytes


@pytest.mark.parametrize(
    ("metadata_generation", "binding_generation", "expected_writes"),
    [
        (1, 1, ("metadata", "binding", "metadata")),
        (2, 1, ("binding", "metadata")),
        (2, 2, ("metadata",)),
    ],
    ids=["S2", "S3", "S4"],
)
def test_recovery_completes_each_supported_suffix_and_replays_as_noop(
    tmp_path: Path,
    metadata_generation: int,
    binding_generation: int,
    expected_writes: tuple[str, ...],
) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    marker = _seed_recovery_state(
        fixture,
        target,
        metadata_generation=metadata_generation,
        binding_generation=binding_generation,
    )
    writes: list[str] = []

    def write_bytes(path: Path, data: bytes) -> None:
        writes.append(
            "binding"
            if path == fixture.binding_path
            else "metadata"
            if path == fixture.paths.BRAIN_METADATA
            else "other"
        )
        atomic_replace_bytes(path, data)

    recovered = _coordinator(
        fixture,
        persistence=TransitionPersistence(write_bytes=write_bytes),
    ).recover_pending_knowledge_create()

    assert recovered == marker.transition_id
    assert _target_path(fixture, knowledge).read_bytes() == target.after_bytes
    assert _read_metadata(fixture).generation == 2
    assert _read_metadata(fixture).pending_transition is None
    assert _read_binding(fixture).accepted_generation == 2
    assert _inspector(fixture).inspect().state is BrainTrustState.TRUSTED_CURRENT
    assert tuple(writes) == expected_writes

    after = _recovery_snapshot(fixture)
    with pytest.raises(BrainTrustNoRecoverableTransitionError):
        _coordinator(fixture).recover_pending_knowledge_create()
    assert _recovery_snapshot(fixture) == after


@pytest.mark.parametrize(
    ("call_number", "expected_metadata_generation", "expected_binding_generation"),
    [
        (1, 1, 1),
        (2, 2, 1),
        (3, 2, 2),
    ],
    ids=["metadata N+1", "binding N+1", "marker clear"],
)
def test_recovery_failures_preserve_inspectable_pending_evidence(
    tmp_path: Path,
    call_number: int,
    expected_metadata_generation: int,
    expected_binding_generation: int,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    _seed_recovery_state(fixture, target)

    with pytest.raises(BrainTrustRecoveryExecutionError):
        _coordinator(
            fixture,
            persistence=_fail_on_call(call_number),
        ).recover_pending_knowledge_create()

    assert _target_path(fixture, knowledge).read_bytes() == target.after_bytes
    assert _read_metadata(fixture).generation == expected_metadata_generation
    assert _read_binding(fixture).accepted_generation == expected_binding_generation
    assert _read_metadata(fixture).pending_transition is not None
    assert _inspector(fixture).inspect().state is BrainTrustState.TRANSITION_PENDING


def test_recovery_post_write_verification_failure_preserves_pending_state(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, knowledge, target = _target(fixture)
    _seed_recovery_state(fixture, target)

    def fail_verification() -> None:
        raise RuntimeError("injected recovery verification failure")

    with pytest.raises(BrainTrustRecoveryExecutionError):
        _coordinator(
            fixture,
            post_write_verifier=fail_verification,
        ).recover_pending_knowledge_create()

    assert _target_path(fixture, knowledge).read_bytes() == target.after_bytes
    assert _read_metadata(fixture).generation == 2
    assert _read_binding(fixture).accepted_generation == 1
    assert _read_metadata(fixture).pending_transition is not None


@pytest.mark.parametrize(
    "case",
    [
        "no-marker",
        "foreign",
        "malformed-metadata",
        "malformed-binding",
        "unsupported-operation",
        "multiple-targets",
        "non-create",
        "unrecognized-path",
        "hash-mismatch",
        "generations-outside-suffix",
        "binding-ahead",
        "untrusted-ahead-without-pending",
    ],
)
def test_recovery_eligibility_rejects_invalid_evidence_without_writes(
    tmp_path: Path,
    case: str,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, _knowledge, target = _target(fixture)

    if case == "no-marker":
        _metadata(fixture)
        _binding(fixture)
    elif case == "foreign":
        _seed_recovery_state(fixture, target, target_exists=True, binding_brain_id=FOREIGN_BRAIN_ID)
    elif case == "malformed-metadata":
        fixture.paths.BRAIN_METADATA.write_bytes(b"{")
        _binding(fixture)
    elif case == "malformed-binding":
        _seed_recovery_state(fixture, target)
        fixture.binding_path.write_bytes(b"{")
    elif case == "unsupported-operation":
        marker = _recovery_transition(target, operation_kind=TransitionOperationKind.RESTORE)
        _seed_recovery_state(fixture, target, transition=marker)
    elif case == "multiple-targets":
        second = TargetDescriptor(
            relative_path="knowledge/66666666-6666-4666-8666-666666666666.json",
            action=TargetAction.CREATE,
            after_sha256="b" * 64,
        )
        marker = _recovery_transition(
            target,
            targets=(_recovery_transition(target).targets[0], second),
        )
        _seed_recovery_state(fixture, target, target_exists=False, transition=marker)
    elif case == "non-create":
        descriptor = TargetDescriptor(
            relative_path=target.relative_path,
            action=TargetAction.REPLACE,
            before_sha256="a" * 64,
            after_sha256=hashlib.sha256(target.after_bytes or b"").hexdigest(),
        )
        marker = _recovery_transition(target, targets=(descriptor,))
        _seed_recovery_state(fixture, target, target_exists=True, transition=marker)
    elif case == "unrecognized-path":
        descriptor = TargetDescriptor(
            relative_path=f"playbooks/{_knowledge.id}.json",
            action=TargetAction.CREATE,
            after_sha256="c" * 64,
        )
        marker = _recovery_transition(target, targets=(descriptor,))
        _seed_recovery_state(fixture, target, target_exists=False, transition=marker)
    elif case == "hash-mismatch":
        _seed_recovery_state(fixture, target)
        _target_path(fixture, _knowledge).write_bytes(b"wrong target bytes")
    elif case == "generations-outside-suffix":
        marker = _recovery_transition(target)
        _seed_recovery_state(
            fixture,
            target,
            metadata_generation=3,
            binding_generation=3,
            transition=marker,
        )
    elif case == "binding-ahead":
        _seed_recovery_state(fixture, target, binding_generation=2)
    elif case == "untrusted-ahead-without-pending":
        _metadata(fixture, generation=2)
        _binding(fixture, generation=1)
    else:
        raise AssertionError(f"Unhandled recovery test case: {case}")

    before = _recovery_snapshot(fixture)

    with pytest.raises(
        (
            BrainTrustNoRecoverableTransitionError,
            BrainTrustUnsupportedRecoveryError,
            BrainTrustUnsafeRecoveryError,
        )
    ):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _recovery_snapshot(fixture) == before


def test_recovery_rejects_create_marker_with_before_hash_without_writes(tmp_path: Path) -> None:
    fixture = _trusted_fixture(tmp_path)
    _repository, _knowledge, target = _target(fixture)
    marker = _recovery_transition(target)
    raw = _metadata(fixture, pending_transition=marker).model_dump(mode="json")
    raw["pending_transition"]["targets"][0]["before_sha256"] = "a" * 64
    fixture.paths.BRAIN_METADATA.write_text(json.dumps(raw), encoding="utf-8")
    _binding(fixture)
    before = _recovery_snapshot(fixture)

    with pytest.raises(BrainTrustUnsafeRecoveryError):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _recovery_snapshot(fixture) == before
