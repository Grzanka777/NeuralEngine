from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from neural_engine.application.brain_trust_inspector import BrainTrustInspector, BrainTrustState
from neural_engine.application.brain_trust_transition import (
    BrainTrustTransitionExecutionError,
    BrainTrustUnsafeRecoveryError,
)
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
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    EvolutionProposal,
    EvolutionProposalStatus,
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
    Playbook,
    PlaybookEffectiveness,
    PlaybookEvaluation,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
    PlaybookRevisionApplication,
    PlaybookRun,
)
from neural_engine.infrastructure.durability import atomic_replace_bytes
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)
from neural_engine.infrastructure.json_decision_action_repository import (
    JsonDecisionActionRepository,
)
from neural_engine.infrastructure.json_decision_outcome_repository import (
    JsonDecisionOutcomeRepository,
)
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository
from neural_engine.infrastructure.json_decision_review_repository import (
    JsonDecisionReviewRepository,
)
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository
from neural_engine.infrastructure.json_playbook_evaluation_repository import (
    JsonPlaybookEvaluationRepository,
)
from neural_engine.infrastructure.json_playbook_repository import JsonPlaybookRepository
from neural_engine.infrastructure.json_playbook_revision_activation_repository import (
    JsonPlaybookRevisionActivationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_application_repository import (
    JsonPlaybookRevisionApplicationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_repository import (
    JsonPlaybookRevisionRepository,
)
from neural_engine.infrastructure.json_playbook_run_repository import JsonPlaybookRunRepository
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe
from neural_engine.infrastructure.local_brain_trust_transition import (
    LocalBrainTrustTransitionCoordinator,
    TransitionPersistence,
)
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")


@dataclass(frozen=True, slots=True)
class TrustFixture:
    paths: NeuralPaths
    binding_path: Path


@dataclass(frozen=True, slots=True)
class WriterSpec:
    name: str
    record: Any
    repository: Any
    path: Path


def _id(value: int) -> UUID:
    return UUID(int=value)


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
    generation: int = 1,
    pending_transition: PendingTransition | None = None,
) -> None:
    value = BrainMetadata(
        metadata_format=BRAIN_TRUST_METADATA_FORMAT,
        brain_id=BRAIN_ID,
        generation=generation,
        pending_transition=pending_transition,
    )
    fixture.paths.BRAIN_METADATA.write_bytes(value.model_dump_json(indent=2).encode("utf-8"))


def _binding(fixture: TrustFixture, *, generation: int = 1) -> None:
    value = ExternalTrustBinding(
        binding_format=BRAIN_TRUST_BINDING_FORMAT,
        expected_brain_id=BRAIN_ID,
        accepted_generation=generation,
    )
    fixture.binding_path.write_bytes(value.model_dump_json(indent=2).encode("utf-8"))


def _trusted_fixture(tmp_path: Path) -> TrustFixture:
    fixture = _fixture(tmp_path)
    _metadata(fixture)
    _binding(fixture)
    return fixture


def _coordinator(
    fixture: TrustFixture,
    *,
    persistence: TransitionPersistence | None = None,
    post_write_verifier: Callable[[], None] | None = None,
) -> LocalBrainTrustTransitionCoordinator:
    return LocalBrainTrustTransitionCoordinator(
        fixture.paths,
        BrainTrustInspector(
            lambda: fixture.paths,
            LocalBrainTrustProbe(binding_path=fixture.binding_path),
        ),
        binding_path=fixture.binding_path,
        persistence=persistence,
        transition_id_factory=lambda: _id(100),
        post_write_verifier=post_write_verifier,
    )


def _writer_specs(fixture: TrustFixture) -> list[WriterSpec]:
    observation = Observation(id=_id(1), content="Observation", tags=["source"])
    experience = Experience(
        id=_id(2),
        title="Experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation.id],
    )
    knowledge = Knowledge(
        id=_id(3),
        statement="Knowledge",
        rationale="Rationale",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience.id],
    )
    playbook = Playbook(
        id=_id(4),
        title="Playbook",
        situation="Situation",
        objective="Objective",
        steps=["Step"],
        success_criteria=["Criterion"],
        knowledge_ids=[knowledge.id],
    )
    run = PlaybookRun(
        id=_id(5),
        playbook_id=playbook.id,
        situation="Run situation",
        actions_taken=["Run action"],
        outcome="Run outcome",
        success=True,
    )
    evaluation = PlaybookEvaluation(
        id=_id(6),
        run_id=run.id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["Finding"],
    )
    proposal = EvolutionProposal(
        id=_id(7),
        playbook_id=playbook.id,
        evaluation_ids=[evaluation.id],
        summary="Proposal",
        rationale="Rationale",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
        status=EvolutionProposalStatus.DRAFT,
    )
    revision = PlaybookRevision(
        id=_id(8),
        playbook_id=playbook.id,
        proposal_id=proposal.id,
        title="Revision",
        situation="Situation",
        objective="Objective",
        steps=["Step"],
        success_criteria=["Criterion"],
        knowledge_ids=[knowledge.id],
    )
    activation = PlaybookRevisionActivation(
        id=_id(9),
        playbook_id=playbook.id,
        revision_id=revision.id,
        proposal_id=proposal.id,
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        reason="Reason",
    )
    application = PlaybookRevisionApplication(
        id=_id(10),
        playbook_id=playbook.id,
        revision_id=revision.id,
        proposal_id=proposal.id,
        reason="Application reason",
    )
    decision = Decision(
        id=_id(11),
        project_key="project",
        title="Decision",
        objective="Objective",
        context_summary="Context",
        alternatives=("A", "B"),
        proposed_option="A",
        rationale="Rationale",
        proposed_by="actor",
        idempotency_key="decision-key",
    )
    acceptance = DecisionAcceptance(
        id=_id(12),
        decision_id=decision.id,
        accepted_by="actor",
        reason="Reason",
        idempotency_key="acceptance-key",
    )
    action = DecisionAction(
        id=_id(13),
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_type="type",
        summary="Summary",
        performed_by="actor",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        idempotency_key="action-key",
    )
    outcome = DecisionOutcome(
        id=_id(14),
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_ids=(action.id,),
        result=DecisionOutcomeResult.SUCCEEDED,
        summary="Summary",
        validated_by="actor",
        validated_at=datetime(2026, 1, 2, tzinfo=UTC),
        idempotency_key="outcome-key",
    )
    review = DecisionReview(
        id=_id(15),
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        outcome_ids=(outcome.id,),
        reviewed_by="actor",
        reviewed_at=datetime(2026, 1, 3, tzinfo=UTC),
        assessment=DecisionReviewAssessment.SOUND,
        summary="Summary",
        findings=("Finding",),
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="review-key",
    )

    return [
        WriterSpec(
            "observation",
            observation,
            JsonObservationRepository(paths=fixture.paths),
            fixture.paths.OBSERVATIONS / f"{observation.id}.json",
        ),
        WriterSpec(
            "experience",
            experience,
            JsonExperienceRepository(paths=fixture.paths),
            fixture.paths.EXPERIENCES / f"{experience.id}.json",
        ),
        WriterSpec(
            "knowledge",
            knowledge,
            JsonKnowledgeRepository(paths=fixture.paths),
            fixture.paths.KNOWLEDGE / f"{knowledge.id}.json",
        ),
        WriterSpec(
            "playbook",
            playbook,
            JsonPlaybookRepository(paths=fixture.paths),
            fixture.paths.PLAYBOOKS / f"{playbook.id}.json",
        ),
        WriterSpec(
            "evaluation",
            evaluation,
            JsonPlaybookEvaluationRepository(paths=fixture.paths),
            fixture.paths.PLAYBOOK_EVALUATIONS / f"{evaluation.id}.json",
        ),
        WriterSpec(
            "proposal",
            proposal,
            JsonEvolutionProposalRepository(paths=fixture.paths),
            fixture.paths.EVOLUTION_PROPOSALS / f"{proposal.id}.json",
        ),
        WriterSpec(
            "activation",
            activation,
            JsonPlaybookRevisionActivationRepository(paths=fixture.paths),
            fixture.paths.PLAYBOOK_REVISION_ACTIVATIONS / f"{activation.id}.json",
        ),
        WriterSpec(
            "application",
            application,
            JsonPlaybookRevisionApplicationRepository(paths=fixture.paths),
            fixture.paths.PLAYBOOK_REVISION_APPLICATIONS / f"{application.id}.json",
        ),
        WriterSpec(
            "revision",
            revision,
            JsonPlaybookRevisionRepository(paths=fixture.paths),
            fixture.paths.PLAYBOOK_REVISIONS / f"{revision.id}.json",
        ),
        WriterSpec(
            "run",
            run,
            JsonPlaybookRunRepository(paths=fixture.paths),
            fixture.paths.PLAYBOOK_RUNS / f"{run.id}.json",
        ),
        WriterSpec(
            "decision",
            decision,
            JsonDecisionRepository(paths=fixture.paths),
            fixture.paths.DECISIONS / f"{decision.id}.json",
        ),
        WriterSpec(
            "acceptance",
            acceptance,
            JsonDecisionAcceptanceRepository(paths=fixture.paths),
            fixture.paths.DECISION_ACCEPTANCES / f"{acceptance.id}.json",
        ),
        WriterSpec(
            "action",
            action,
            JsonDecisionActionRepository(paths=fixture.paths),
            fixture.paths.DECISION_ACTIONS / f"{action.id}.json",
        ),
        WriterSpec(
            "outcome",
            outcome,
            JsonDecisionOutcomeRepository(paths=fixture.paths),
            fixture.paths.DECISION_OUTCOMES / f"{outcome.id}.json",
        ),
        WriterSpec(
            "review",
            review,
            JsonDecisionReviewRepository(paths=fixture.paths),
            fixture.paths.DECISION_REVIEWS / f"{review.id}.json",
        ),
    ]


def _target(spec: WriterSpec) -> ControlledMutationTarget:
    target = spec.repository.controlled_create_target(spec.record)
    assert isinstance(target, ControlledMutationTarget)
    return target


def _pending_transition(target: ControlledMutationTarget) -> PendingTransition:
    return _pending_transition_for_hash(
        target,
        hashlib.sha256(target.after_bytes or b"").hexdigest(),
    )


def _pending_transition_for_hash(
    target: ControlledMutationTarget,
    after_sha256: str,
) -> PendingTransition:
    return PendingTransition(
        transition_id=_id(100),
        brain_id=BRAIN_ID,
        from_generation=1,
        to_generation=2,
        operation_kind=TransitionOperationKind.ORDINARY_MUTATION,
        targets=(
            TargetDescriptor(
                relative_path=target.relative_path,
                action=target.action,
                after_sha256=after_sha256,
            ),
        ),
    )


def _seed_recovery(
    fixture: TrustFixture,
    target: ControlledMutationTarget,
    *,
    metadata_generation: int = 1,
    binding_generation: int = 1,
    target_exists: bool = True,
) -> None:
    if target_exists:
        target.publish()
    _metadata(
        fixture,
        generation=metadata_generation,
        pending_transition=_pending_transition(target),
    )
    _binding(fixture, generation=binding_generation)


def _snapshot(fixture: TrustFixture) -> tuple[dict[str, bytes], bytes]:
    files = {
        path.relative_to(fixture.paths.HOME).as_posix(): path.read_bytes()
        for path in fixture.paths.HOME.rglob("*")
        if path.is_file()
    }
    return files, fixture.binding_path.read_bytes()


@pytest.mark.parametrize(
    "spec_index",
    range(15),
    ids=[
        "observation",
        "experience",
        "knowledge",
        "playbook",
        "evaluation",
        "proposal",
        "activation",
        "application",
        "revision",
        "run",
        "decision",
        "acceptance",
        "action",
        "outcome",
        "review",
    ],
)
def test_every_supported_store_exposes_one_brain_relative_create_target(
    tmp_path: Path,
    spec_index: int,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    spec = _writer_specs(fixture)[spec_index]

    target = _target(spec)

    assert target.action is TargetAction.CREATE
    assert target.relative_path == spec.path.relative_to(fixture.paths.BRAIN).as_posix()
    assert target.after_bytes is not None
    assert hashlib.sha256(target.after_bytes).hexdigest()
    assert not spec.path.exists()

    target.publish()

    assert spec.path.read_bytes() == target.after_bytes
    assert spec.repository.get_by_id(spec.record.id) == spec.record
    assert sorted(spec.path.parent.glob("*.json")) == [spec.path]
    assert list(spec.path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize("spec_index", range(15), ids=[str(index) for index in range(15)])
@pytest.mark.parametrize(
    ("metadata_generation", "binding_generation"),
    [(1, 1), (2, 1), (2, 2)],
    ids=["S2", "S3", "S4"],
)
def test_every_supported_store_recovers_s2_s3_s4(
    tmp_path: Path,
    spec_index: int,
    metadata_generation: int,
    binding_generation: int,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    spec = _writer_specs(fixture)[spec_index]
    target = _target(spec)
    _seed_recovery(
        fixture,
        target,
        metadata_generation=metadata_generation,
        binding_generation=binding_generation,
    )

    _coordinator(fixture).recover_pending_knowledge_create()

    assert spec.path.read_bytes() == target.after_bytes
    assert (
        BrainMetadata.model_validate_json(fixture.paths.BRAIN_METADATA.read_bytes()).generation == 2
    )
    assert (
        BrainMetadata.model_validate_json(
            fixture.paths.BRAIN_METADATA.read_bytes()
        ).pending_transition
        is None
    )
    assert (
        ExternalTrustBinding.model_validate_json(
            fixture.binding_path.read_bytes()
        ).accepted_generation
        == 2
    )
    assert BrainTrustState.TRUSTED_CURRENT is _coordinator(fixture)._inspector.inspect().state


@pytest.mark.parametrize("spec_index", range(15), ids=[str(index) for index in range(15)])
def test_every_supported_store_rejects_s1_without_writes(tmp_path: Path, spec_index: int) -> None:
    fixture = _trusted_fixture(tmp_path)
    spec = _writer_specs(fixture)[spec_index]
    target = _target(spec)
    _seed_recovery(fixture, target, target_exists=False)
    before = _snapshot(fixture)

    with pytest.raises(BrainTrustUnsafeRecoveryError, match="S1_REJECTED_INSUFFICIENT_EVIDENCE"):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _snapshot(fixture) == before


@pytest.mark.parametrize(
    ("failure", "metadata_generation", "binding_generation", "target_exists", "marker"),
    [
        ("F1", 1, 1, False, False),
        ("F2", 1, 1, False, True),
        ("F3", 1, 1, True, True),
        ("F4", 2, 1, True, True),
        ("F5", 2, 1, True, True),
        ("F6", 2, 2, True, True),
    ],
    ids=["F1-marker", "F2-target", "F3-metadata", "F4-verification", "F5-binding", "F6-clear"],
)
@pytest.mark.parametrize("spec_index", range(15), ids=[str(index) for index in range(15)])
def test_every_supported_store_preserves_f1_to_f6_evidence(
    tmp_path: Path,
    failure: str,
    metadata_generation: int,
    binding_generation: int,
    target_exists: bool,
    marker: bool,
    spec_index: int,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    spec = _writer_specs(fixture)[spec_index]
    target = _target(spec)

    if failure == "F2":
        failing_target = ControlledMutationTarget(
            relative_path=target.relative_path,
            action=target.action,
            after_bytes=target.after_bytes,
            publish=lambda: (_ for _ in ()).throw(OSError("injected target failure")),
        )
    else:
        failing_target = target

    call_number = {"F1": 1, "F3": 2, "F5": 3, "F6": 4}.get(failure)
    persistence = None
    if call_number is not None:
        calls = 0

        def write_bytes(path: Path, data: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == call_number:
                raise OSError(f"injected persistence failure {failure}")
            atomic_replace_bytes(path, data)

        persistence = TransitionPersistence(write_bytes=write_bytes)

    verifier = None
    if failure == "F4":

        def failing_verifier() -> None:
            raise RuntimeError("injected verification failure")

        verifier = failing_verifier

    with pytest.raises(BrainTrustTransitionExecutionError) as raised:
        _coordinator(
            fixture,
            persistence=persistence,
            post_write_verifier=verifier,
        ).execute(failing_target)

    assert spec.path.exists() is target_exists
    if target_exists:
        assert spec.path.read_bytes() == target.after_bytes
    metadata = BrainMetadata.model_validate_json(fixture.paths.BRAIN_METADATA.read_bytes())
    binding = ExternalTrustBinding.model_validate_json(fixture.binding_path.read_bytes())
    assert metadata.generation == metadata_generation
    assert binding.accepted_generation == binding_generation
    assert (metadata.pending_transition is not None) is marker
    expected_state = (
        BrainTrustState.TRUSTED_CURRENT if failure == "F1" else BrainTrustState.TRANSITION_PENDING
    )
    assert _coordinator(fixture)._inspector.inspect().state is expected_state
    assert "failed" in str(raised.value)


@pytest.mark.parametrize("spec_index", range(15), ids=[str(index) for index in range(15)])
def test_every_supported_store_rejects_target_symlink_without_writes(
    tmp_path: Path,
    spec_index: int,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    spec = _writer_specs(fixture)[spec_index]
    target = _target(spec)
    _seed_recovery(fixture, target)
    alias = spec.path.with_name("alias.json")
    alias.write_bytes(target.after_bytes or b"")
    spec.path.unlink()
    spec.path.symlink_to(alias)
    before = _snapshot(fixture)

    with pytest.raises(BrainTrustUnsafeRecoveryError, match="symbolic link"):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _snapshot(fixture) == before
    assert spec.path.is_symlink()


@pytest.mark.parametrize("spec_index", range(15), ids=[str(index) for index in range(15)])
def test_every_supported_store_rejects_filename_payload_identity_mismatch(
    tmp_path: Path,
    spec_index: int,
) -> None:
    fixture = _trusted_fixture(tmp_path)
    spec = _writer_specs(fixture)[spec_index]
    target = _target(spec)
    wrong_record = spec.record.model_copy(update={"id": _id(1000 + spec_index)})
    wrong_target = _target(
        WriterSpec(
            spec.name, wrong_record, spec.repository, spec.path.with_name(f"{wrong_record.id}.json")
        )
    )
    spec.path.write_bytes(wrong_target.after_bytes or b"")
    marker = _pending_transition_for_hash(
        target,
        hashlib.sha256(wrong_target.after_bytes or b"").hexdigest(),
    )
    _metadata(fixture, pending_transition=marker)
    _binding(fixture)
    before = _snapshot(fixture)

    with pytest.raises(
        BrainTrustUnsafeRecoveryError, match="identity|not valid current-store data"
    ):
        _coordinator(fixture).recover_pending_knowledge_create()

    assert _snapshot(fixture) == before
