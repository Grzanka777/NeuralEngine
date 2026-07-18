import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from neural_engine.application.decision_lifecycle_service import (
    DecisionLifecycleService,
    DecisionLifecycleState,
)
from neural_engine.application.decision_review_service import DecisionReviewService
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
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


@pytest.mark.parametrize(
    ("result", "expected_state"),
    [
        (DecisionOutcomeResult.SUCCEEDED, DecisionLifecycleState.SUCCEEDED),
        (DecisionOutcomeResult.FAILED, DecisionLifecycleState.FAILED),
        (DecisionOutcomeResult.PARTIAL, DecisionLifecycleState.PARTIAL),
        (DecisionOutcomeResult.UNKNOWN, DecisionLifecycleState.OUTCOME_UNKNOWN),
    ],
)
def test_review_creation_does_not_change_outcome_derived_lifecycle(
    tmp_path: Path,
    result: DecisionOutcomeResult,
    expected_state: DecisionLifecycleState,
) -> None:
    decision_repository = JsonDecisionRepository(tmp_path / "decisions")
    acceptance_repository = JsonDecisionAcceptanceRepository(tmp_path / "acceptances")
    action_repository = JsonDecisionActionRepository(tmp_path / "actions")
    outcome_repository = JsonDecisionOutcomeRepository(tmp_path / "outcomes")
    review_repository = JsonDecisionReviewRepository(tmp_path / "reviews")
    now = datetime.now(UTC)
    decision = Decision(
        project_key="NeuralEngine",
        title="Protect lifecycle",
        objective="Keep review orthogonal",
        context_summary="Interpretation must not replace factual state.",
        alternatives=("Orthogonal review", "Reviewed state"),
        proposed_option="Orthogonal review",
        rationale="Factual outcomes remain visible.",
        proposed_by="codex",
        idempotency_key="decision-boundary",
    )
    acceptance = DecisionAcceptance(
        decision_id=decision.id,
        accepted_by="owner",
        reason="Proceed.",
        idempotency_key="acceptance-boundary",
    )
    action = DecisionAction(
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_type="test",
        summary="Ran validation.",
        performed_by="pytest",
        started_at=now - timedelta(hours=2),
        idempotency_key="action-boundary",
    )
    outcome = DecisionOutcome(
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_ids=(action.id,),
        result=result,
        summary="Recorded factual result.",
        validated_by="pytest",
        validated_at=now - timedelta(hours=1),
        idempotency_key="outcome-boundary",
    )
    decision_repository.save(decision)
    acceptance_repository.save(acceptance)
    action_repository.save(action)
    outcome_repository.save(outcome)
    lifecycle = DecisionLifecycleService(
        decision_repository,
        acceptance_repository,
        action_repository,
        outcome_repository,
    )

    assert lifecycle.state(decision.id) is expected_state
    review = DecisionReviewService(
        review_repository,
        decision_repository,
        acceptance_repository,
        outcome_repository,
    ).add(
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        outcome_ids=[outcome.id],
        reviewed_by="owner",
        reviewed_at=now,
        assessment=DecisionReviewAssessment.MIXED,
        summary="The factual state remains authoritative.",
        findings=["Review is interpretive history."],
        candidate_lessons=["Keep lifecycle and review separate."],
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="review-boundary",
    )

    assert lifecycle.state(decision.id) is expected_state
    assert review_repository.load_all() == [review]
    assert {item.value for item in DecisionLifecycleState} == {
        "proposed",
        "accepted",
        "in_progress",
        "succeeded",
        "failed",
        "partial",
        "outcome_unknown",
    }
    assert {path.name for path in tmp_path.iterdir()} == {
        "decisions",
        "acceptances",
        "actions",
        "outcomes",
        "reviews",
    }


def test_lifecycle_has_no_decision_review_dependency() -> None:
    parameters = inspect.signature(DecisionLifecycleService).parameters
    assert "review_repository" not in parameters
    assert "reviewed" not in {state.value for state in DecisionLifecycleState}


def test_review_service_has_no_learning_or_consigliere_boundary() -> None:
    source = inspect.getsource(DecisionReviewService).casefold()
    assert "consigliere" not in source
    assert set(DecisionReviewService.add.__annotations__) == {
        "decision_id",
        "acceptance_id",
        "outcome_ids",
        "reviewed_by",
        "reviewed_at",
        "assessment",
        "summary",
        "findings",
        "confidence",
        "idempotency_key",
        "candidate_lessons",
        "evidence_references",
        "tags",
        "return",
    }
