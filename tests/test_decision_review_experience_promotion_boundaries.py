import inspect
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.application.decision_lifecycle_service import DecisionLifecycleService
from neural_engine.application.decision_review_service import (
    DecisionReviewDecisionNotFoundError,
    DecisionReviewService,
)
from neural_engine.application.experience_service import (
    DecisionReviewPromotionSelector,
    ExperienceService,
)
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    DecisionReviewPromotionSourceKind,
    ExperienceResult,
)
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
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository

T_ACTION = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
T_OUTCOME = datetime(2026, 7, 18, 11, 0, tzinfo=UTC)
T_REVIEW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
T_RECORDED = datetime(2026, 7, 18, 13, 0, tzinfo=UTC)


def test_promotion_uses_validated_review_boundary_without_changing_lifecycle(
    tmp_path: Path,
) -> None:
    decision_repository = JsonDecisionRepository(tmp_path / "decisions")
    acceptance_repository = JsonDecisionAcceptanceRepository(tmp_path / "acceptances")
    action_repository = JsonDecisionActionRepository(tmp_path / "actions")
    outcome_repository = JsonDecisionOutcomeRepository(tmp_path / "outcomes")
    review_repository = JsonDecisionReviewRepository(tmp_path / "reviews")
    experience_repository = JsonExperienceRepository(tmp_path / "experiences")
    decision = Decision(
        project_key="NeuralEngine",
        title="Promote reviewed learning",
        objective="Preserve explicit authority",
        context_summary="A reviewed statement may become Experience.",
        alternatives=("Explicit promotion", "Automatic learning"),
        proposed_option="Explicit promotion",
        rationale="Promotion remains auditable.",
        proposed_by="architect",
        idempotency_key="decision-promotion-boundary",
    )
    acceptance = DecisionAcceptance(
        decision_id=decision.id,
        accepted_by="owner",
        reason="Proceed explicitly.",
        idempotency_key="acceptance-promotion-boundary",
    )
    action = DecisionAction(
        recorded_at=T_RECORDED,
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_type="implementation",
        summary="Implemented explicit promotion.",
        performed_by="codex",
        started_at=T_ACTION,
        completed_at=T_OUTCOME,
        idempotency_key="action-promotion-boundary",
    )
    outcome = DecisionOutcome(
        recorded_at=T_RECORDED,
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_ids=(action.id,),
        result=DecisionOutcomeResult.SUCCEEDED,
        summary="Promotion foundation validated.",
        validated_by="pytest",
        validated_at=T_OUTCOME,
        idempotency_key="outcome-promotion-boundary",
    )
    review = DecisionReview(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        recorded_at=T_RECORDED,
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        outcome_ids=(outcome.id,),
        reviewed_by="reviewer",
        reviewed_at=T_REVIEW,
        assessment=DecisionReviewAssessment.SOUND,
        summary="Explicit promotion is sound.",
        findings=("Keep promotion explicit.",),
        candidate_lessons=("Separate Experience from Knowledge.",),
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="review-promotion-boundary",
    )
    decision_repository.save(decision)
    acceptance_repository.save(acceptance)
    action_repository.save(action)
    outcome_repository.save(outcome)
    review_repository.save(review)
    review_service = DecisionReviewService(
        review_repository,
        decision_repository,
        acceptance_repository,
        outcome_repository,
    )
    lifecycle = DecisionLifecycleService(
        decision_repository,
        acceptance_repository,
        action_repository,
        outcome_repository,
    )
    service = ExperienceService(
        experience_repository,
        JsonObservationRepository(tmp_path / "observations"),
        review_service,
    )
    state_before = lifecycle.state(decision.id)

    experience = service.add_from_decision_review(
        decision_review_id=review.id,
        source_selectors=[
            DecisionReviewPromotionSelector(DecisionReviewPromotionSourceKind.CANDIDATE_LESSON, 0)
        ],
        promoted_by="learning-owner",
        promotion_reason="The lesson is operationally reusable.",
        idempotency_key="promotion-boundary",
        title="Explicit lesson",
        context="Reviewed Decision",
        action="Promote candidate lesson",
        outcome="Experience persisted",
        result=ExperienceResult.SUCCESS,
    )

    assert lifecycle.state(decision.id) is state_before
    assert experience_repository.load_all() == [experience]
    assert {path.name for path in tmp_path.iterdir()} == {
        "decisions",
        "acceptances",
        "actions",
        "outcomes",
        "reviews",
        "experiences",
    }


def test_malformed_persisted_review_relations_fail_through_existing_show_boundary(
    tmp_path: Path,
) -> None:
    review_repository = JsonDecisionReviewRepository(tmp_path / "reviews")
    review = DecisionReview(
        recorded_at=T_RECORDED,
        decision_id=UUID("33333333-3333-3333-3333-333333333333"),
        acceptance_id=UUID("44444444-4444-4444-4444-444444444444"),
        outcome_ids=(UUID("55555555-5555-5555-5555-555555555555"),),
        reviewed_by="reviewer",
        reviewed_at=T_REVIEW,
        assessment=DecisionReviewAssessment.MIXED,
        summary="Persisted relation is invalid.",
        findings=("Fail closed.",),
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="invalid-review",
    )
    review_repository.save(review)
    experience_repository = JsonExperienceRepository(tmp_path / "experiences")
    service = ExperienceService(
        experience_repository,
        JsonObservationRepository(tmp_path / "observations"),
        DecisionReviewService(
            review_repository,
            JsonDecisionRepository(tmp_path / "decisions"),
            JsonDecisionAcceptanceRepository(tmp_path / "acceptances"),
            JsonDecisionOutcomeRepository(tmp_path / "outcomes"),
        ),
    )

    with pytest.raises(DecisionReviewDecisionNotFoundError):
        service.add_from_decision_review(
            decision_review_id=review.id,
            source_selectors=[
                DecisionReviewPromotionSelector(DecisionReviewPromotionSourceKind.FINDING, 0)
            ],
            promoted_by="owner",
            promotion_reason="Attempt promotion.",
            idempotency_key="invalid-promotion",
            title="Rejected",
            context="Invalid graph",
            action="Fail closed",
            outcome="No Experience",
            result=ExperienceResult.FAILURE,
        )
    assert experience_repository.load_all() == []


def test_promotion_service_has_no_downstream_learning_or_consigliere_behavior() -> None:
    source = inspect.getsource(ExperienceService.add_from_decision_review).casefold()

    for forbidden in (
        "knowledge",
        "playbook",
        "evolution",
        "revision",
        "consigliere",
        "lifecycle",
        "evidence",
    ):
        assert forbidden not in source
