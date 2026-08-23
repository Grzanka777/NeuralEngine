from __future__ import annotations

import hashlib
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
    BrainTrustTransitionExecutionError,
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
