from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from neural_engine.application.container import Container
from neural_engine.application.development_evidence_service import (
    DevelopmentEvidenceRecordInput,
    DevelopmentEvidenceRequest,
    DevelopmentEvidenceService,
    DevelopmentEvidenceTrustError,
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
    DecisionOutcomeResult,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    ExperienceResult,
)
from neural_engine.ports.development_evidence_source import (
    DevelopmentEvidenceSnapshot,
    ValidationClaim,
)

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")
TRANSITION_ID = UUID("22222222-2222-4222-8222-222222222222")


class StaticSource:
    def __init__(self, snapshot: DevelopmentEvidenceSnapshot) -> None:
        self.snapshot = snapshot

    def read(
        self,
        *,
        repository_root: str,
        prompt_path: str,
        review_path: str,
        commit_sha: str,
    ) -> DevelopmentEvidenceSnapshot:
        return self.snapshot


class InjectedAfterPublication(RuntimeError):
    pass


def _snapshot() -> DevelopmentEvidenceSnapshot:
    parent = "1" * 40
    commit = "2" * 40
    tree = "3" * 40
    return DevelopmentEvidenceSnapshot(
        repository_identity="NeuralEngine",
        repository_root="/tmp/NeuralEngine",
        prompt_path=".agent-work/prompts/task.md",
        prompt_sha256="sha256:" + "a" * 64,
        prompt_starting_checkpoint=parent,
        review_path=".agent-work/reviews/review.md",
        review_sha256="sha256:" + "b" * 64,
        review_starting_checkpoint=parent,
        review_outcome="completed",
        review_changed_paths=("src/change.py",),
        review_patch_sha256="sha256:" + "c" * 64,
        validation_claims=(ValidationClaim("uv run pytest", 0, 10),),
        validation_tree_attested=None,
        risks_deviations_blockers=("Blockers: none.",),
        commit_sha=commit,
        commit_parent_sha=parent,
        commit_subject="implement fixture",
        commit_tree_sha=tree,
        commit_changed_paths=("src/change.py",),
        commit_patch_sha256="sha256:" + "c" * 64,
        patch_matches=True,
    )


def _records(*, promotion: bool = False) -> DevelopmentEvidenceRecordInput:
    payload: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Implement local evidence orchestration",
        "objective": "Dogfood existing Decision-family records",
        "context_summary": "Caller-authored bounded interpretation.",
        "alternatives": ("Do nothing", "Apply the bounded implementation"),
        "proposed_option": "Apply the bounded implementation",
        "rationale": "Exercise explicit local evidence flow.",
        "proposed_by": "proposer",
        "accepted_by": "acceptor",
        "acceptance_reason": "Explicit acceptance.",
        "action_type": "implementation",
        "action_summary": "Implemented the selected bounded work.",
        "performed_by": "implementer",
        "started_at": datetime(2026, 7, 20, 10, tzinfo=UTC),
        "completed_at": datetime(2026, 7, 20, 11, tzinfo=UTC),
        "outcome_result": DecisionOutcomeResult.UNKNOWN,
        "outcome_summary": "Caller explicitly classified the factual result as unknown.",
        "validated_by": "validator",
        "validated_at": datetime(2026, 7, 20, 12, tzinfo=UTC),
        "reviewed_by": "reviewer",
        "reviewed_at": datetime(2026, 7, 20, 13, tzinfo=UTC),
        "review_assessment": DecisionReviewAssessment.SOUND,
        "review_summary": "Caller-authored interpretation.",
        "findings": ("The bounded orchestration was exercised.",),
        "candidate_lessons": ("Keep preview and apply separate.",),
        "review_confidence": DecisionReviewConfidence.MEDIUM,
    }
    if promotion:
        payload["promotion"] = {
            "source_selectors": ({"kind": "finding", "index": 0},),
            "promoted_by": "promoter",
            "promotion_reason": "Explicitly selected for reuse.",
            "title": "Local evidence lesson",
            "context": "A completed bounded milestone.",
            "action": "Separate preview from explicit apply.",
            "outcome": "Source identities are revalidated.",
            "result": ExperienceResult.SUCCESS,
        }
    return DevelopmentEvidenceRecordInput.model_validate(payload)


def _request() -> DevelopmentEvidenceRequest:
    return DevelopmentEvidenceRequest(
        repository_root="/tmp/NeuralEngine",
        prompt_path=".agent-work/prompts/task.md",
        review_path=".agent-work/reviews/review.md",
        commit_sha="2" * 40,
    )


def _paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, trusted: bool) -> NeuralPaths:
    user_home = tmp_path / "user-home"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    neural_home = tmp_path / "neural-home"
    neural_home.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(neural_home)})
    Brain(paths).initialize()

    if trusted:
        metadata = BrainMetadata(
            metadata_format=BRAIN_TRUST_METADATA_FORMAT,
            brain_id=BRAIN_ID,
            generation=1,
        )
        binding = ExternalTrustBinding(
            binding_format=BRAIN_TRUST_BINDING_FORMAT,
            expected_brain_id=BRAIN_ID,
            accepted_generation=1,
        )
        paths.BRAIN_METADATA.write_bytes(metadata.model_dump_json(indent=2).encode())
        paths.TRUST_BINDING.parent.mkdir(parents=True, exist_ok=True)
        paths.TRUST_BINDING.write_bytes(binding.model_dump_json(indent=2).encode())

    return paths


def _service(paths: NeuralPaths) -> DevelopmentEvidenceService:
    scoped = Container(paths)
    return DevelopmentEvidenceService(
        StaticSource(_snapshot()),
        scoped.decision_service(),
        scoped.decision_acceptance_service(),
        scoped.decision_action_service(),
        scoped.decision_outcome_service(),
        scoped.decision_review_service(),
        scoped.experience_service(),
    )


def _metadata(paths: NeuralPaths) -> BrainMetadata:
    return BrainMetadata.model_validate_json(paths.BRAIN_METADATA.read_bytes())


def _binding(paths: NeuralPaths) -> ExternalTrustBinding:
    return ExternalTrustBinding.model_validate_json(paths.TRUST_BINDING.read_bytes())


def _counts(paths: NeuralPaths) -> tuple[int, ...]:
    return tuple(len(list(store.glob("*.json"))) for _, store in paths.record_stores)


@pytest.mark.parametrize(
    ("step", "component_attr", "method", "prefix_count"),
    [
        ("Decision", "_decision_service", "add", 1),
        ("Acceptance", "_acceptance_service", "accept", 2),
        ("Action", "_action_service", "add", 3),
        ("Outcome", "_outcome_service", "add", 4),
        ("Review", "_review_service", "add", 5),
    ],
)
def test_trusted_m23_retry_resumes_each_partial_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: str,
    component_attr: str,
    method: str,
    prefix_count: int,
) -> None:
    paths = _paths(monkeypatch, tmp_path, trusted=True)
    service = _service(paths)
    candidate = service.preview(_request(), _records())
    component = getattr(service, component_attr)
    original = cast(Callable[..., object], getattr(component, method))

    def fail_after(*args: object, **kwargs: object) -> object:
        original(*args, **kwargs)
        raise InjectedAfterPublication(step)

    setattr(component, method, fail_after)
    try:
        with pytest.raises(InjectedAfterPublication, match=step):
            service.apply(candidate, authority_confirmed=True)
    finally:
        setattr(component, method, original)

    assert _counts(paths)[-5:] == tuple(1 if prefix_count >= index else 0 for index in range(1, 6))
    assert _metadata(paths).generation == prefix_count + 1
    assert _binding(paths).accepted_generation == prefix_count + 1
    assert _metadata(paths).pending_transition is None

    result = service.apply(candidate, authority_confirmed=True)

    assert result.review.decision_id == result.decision.id
    assert _counts(paths)[-5:] == (1, 1, 1, 1, 1)
    assert _metadata(paths).generation == 6
    assert _binding(paths).accepted_generation == 6
    assert _metadata(paths).pending_transition is None


@pytest.mark.parametrize(
    ("step", "component_attr", "method", "prefix_count"),
    [
        ("Review", "_review_service", "add", 5),
        ("Experience", "_experience_service", "add_from_decision_review", 6),
    ],
)
def test_trusted_m23_optional_experience_is_an_independent_final_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step: str,
    component_attr: str,
    method: str,
    prefix_count: int,
) -> None:
    paths = _paths(monkeypatch, tmp_path, trusted=True)
    service = _service(paths)
    candidate = service.preview(_request(), _records(promotion=True))
    component = getattr(service, component_attr)
    original = cast(Callable[..., object], getattr(component, method))

    def fail_after(*args: object, **kwargs: object) -> object:
        original(*args, **kwargs)
        raise InjectedAfterPublication(step)

    setattr(component, method, fail_after)
    try:
        with pytest.raises(InjectedAfterPublication, match=step):
            service.apply(candidate, authority_confirmed=True)
    finally:
        setattr(component, method, original)

    assert _metadata(paths).generation == prefix_count + 1
    assert _binding(paths).accepted_generation == prefix_count + 1
    assert _metadata(paths).pending_transition is None
    assert len(list(paths.EXPERIENCES.glob("*.json"))) == (1 if prefix_count == 6 else 0)

    result = service.apply(candidate, authority_confirmed=True)

    assert result.experience is not None
    assert len(list(paths.EXPERIENCES.glob("*.json"))) == 1
    assert _metadata(paths).generation == 7
    assert _binding(paths).accepted_generation == 7
    assert _metadata(paths).pending_transition is None


def test_container_composition_keeps_all_m23_component_writers_controlled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _paths(monkeypatch, tmp_path, trusted=True)
    service = Container(paths).development_evidence_service()

    for component_name in (
        "_decision_service",
        "_acceptance_service",
        "_action_service",
        "_outcome_service",
        "_review_service",
        "_experience_service",
    ):
        component = getattr(service, component_name)
        assert component._controlled_writer is not None
        assert component._mutation_coordinator is not None


def test_untrusted_m23_fails_before_first_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _paths(monkeypatch, tmp_path, trusted=False)
    service = _service(paths)
    candidate = service.preview(_request(), _records())

    with pytest.raises(DevelopmentEvidenceTrustError, match="UNADOPTED"):
        service.apply(candidate, authority_confirmed=True)

    assert all(count == 0 for count in _counts(paths)[-5:])
    assert not paths.BRAIN_METADATA.exists()
    assert not paths.TRUST_BINDING.exists()


def test_pending_m23_transition_remains_fail_closed_without_new_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _paths(monkeypatch, tmp_path, trusted=True)
    descriptor = TargetDescriptor(
        relative_path="decisions/33333333-3333-4333-8333-333333333333.json",
        action=TargetAction.CREATE,
        after_sha256="0" * 64,
    )
    pending = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=1,
        to_generation=2,
        operation_kind=TransitionOperationKind.ORDINARY_MUTATION,
        targets=(descriptor,),
    )
    paths.BRAIN_METADATA.write_bytes(
        BrainMetadata(
            metadata_format=BRAIN_TRUST_METADATA_FORMAT,
            brain_id=BRAIN_ID,
            generation=1,
            pending_transition=pending,
        )
        .model_dump_json(indent=2)
        .encode()
    )
    service = _service(paths)
    candidate = service.preview(_request(), _records())

    with pytest.raises(DevelopmentEvidenceTrustError, match="TRANSITION_PENDING"):
        service.apply(candidate, authority_confirmed=True)

    assert _metadata(paths).generation == 1
    assert _metadata(paths).pending_transition == pending
    assert _binding(paths).accepted_generation == 1
    assert all(count == 0 for count in _counts(paths)[-5:])
