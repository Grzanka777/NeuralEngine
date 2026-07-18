from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.application.decision_review_service import (
    DecisionReviewAcceptanceMismatchError,
    DecisionReviewAcceptanceNotFoundError,
    DecisionReviewBeforeOutcomeError,
    DecisionReviewDecisionNotFoundError,
    DecisionReviewIdempotencyAmbiguityError,
    DecisionReviewIdempotencyConflictError,
    DecisionReviewNotFoundError,
    DecisionReviewOutcomeAcceptanceMismatchError,
    DecisionReviewOutcomeDecisionMismatchError,
    DecisionReviewOutcomeNotFoundError,
    DecisionReviewService,
)
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    EvidenceReference,
)
from neural_engine.ports.decision_acceptance_repository import DecisionAcceptanceRepository
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
from neural_engine.ports.decision_repository import DecisionRepository
from neural_engine.ports.decision_review_repository import DecisionReviewRepository

# Fixed UTC timeline for deterministic test fixtures.
# Invariants preserved:
#   outcome.validated_at <= outcome.recorded_at (auto-generated via default factory)
#   max(outcome.validated_at) <= review.reviewed_at
#   review.reviewed_at <= review.recorded_at (auto-generated via default factory)
_T_OUTCOME_VALIDATED = datetime(2026, 7, 18, 11, 0, tzinfo=UTC)
_T_OUTCOME_VALIDATED_LATER = datetime(2026, 7, 18, 11, 30, tzinfo=UTC)
_T_OUTCOME_VALIDATED_TOO_LATE = datetime(2026, 7, 18, 12, 30, tzinfo=UTC)
_T_REVIEW_REVIEWED = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
_T_REVIEW_RECORDED = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)


class DecisionRepo(DecisionRepository):
    def __init__(self, values: list[Decision]) -> None:
        self.values = values

    def save(self, decision: Decision) -> None:
        self.values.append(decision)

    def load_all(self) -> list[Decision]:
        return self.values

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        return next((item for item in self.values if item.id == decision_id), None)


class AcceptanceRepo(DecisionAcceptanceRepository):
    def __init__(self, values: list[DecisionAcceptance]) -> None:
        self.values = values

    def save(self, acceptance: DecisionAcceptance) -> None:
        self.values.append(acceptance)

    def load_all(self) -> list[DecisionAcceptance]:
        return self.values

    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        return next((item for item in self.values if item.id == acceptance_id), None)


class OutcomeRepo(DecisionOutcomeRepository):
    def __init__(self, values: list[DecisionOutcome]) -> None:
        self.values = values

    def save(self, outcome: DecisionOutcome) -> None:
        self.values.append(outcome)

    def load_all(self) -> list[DecisionOutcome]:
        return self.values

    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        return next((item for item in self.values if item.id == outcome_id), None)


class ReviewRepo(DecisionReviewRepository):
    def __init__(self, values: list[DecisionReview] | None = None) -> None:
        self.values = values or []
        self.save_calls: list[DecisionReview] = []

    def save(self, review: DecisionReview) -> None:
        self.save_calls.append(review)
        self.values.append(review)

    def load_all(self) -> list[DecisionReview]:
        return self.values

    def get_by_id(self, review_id: UUID) -> DecisionReview | None:
        return next((item for item in self.values if item.id == review_id), None)


def make_decision(**updates: object) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Review decisions",
        "objective": "Separate facts from interpretation",
        "context_summary": "Outcomes need authorized review.",
        "alternatives": ("Review record", "Mutate outcome"),
        "proposed_option": "Review record",
        "rationale": "Immutable provenance is auditable.",
        "proposed_by": "codex",
        "idempotency_key": "decision-review",
    }
    values.update(updates)
    return Decision.model_validate(values)


def make_acceptance(decision_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "accepted_by": "owner",
        "reason": "Proceed.",
        "idempotency_key": "accept-review",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def make_outcome(decision_id: UUID, acceptance_id: UUID, **updates: object) -> DecisionOutcome:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_ids": (UUID("33333333-3333-3333-3333-333333333333"),),
        "result": DecisionOutcomeResult.SUCCEEDED,
        "summary": "Validation passed.",
        "validated_by": "pytest",
        "validated_at": _T_OUTCOME_VALIDATED,
        "idempotency_key": "outcome-review",
    }
    values.update(updates)
    return DecisionOutcome.model_validate(values)


def add_values(
    decision: Decision, acceptance: DecisionAcceptance, outcomes: list[DecisionOutcome]
) -> dict[str, object]:
    return {
        "decision_id": decision.id,
        "acceptance_id": acceptance.id,
        "outcome_ids": [outcome.id for outcome in outcomes],
        "reviewed_by": "architecture-owner",
        "reviewed_at": _T_REVIEW_REVIEWED,
        "assessment": DecisionReviewAssessment.SOUND,
        "summary": "The decision remains defensible.",
        "findings": ["The implementation preserved boundaries."],
        "candidate_lessons": ["Keep lifecycle projection independent."],
        "evidence_references": [EvidenceReference(kind="review", locator="review:1")],
        "confidence": DecisionReviewConfidence.HIGH,
        "idempotency_key": "review-1",
        "tags": ["architecture"],
    }


def make_service(
    decisions: list[Decision],
    acceptances: list[DecisionAcceptance],
    outcomes: list[DecisionOutcome],
    reviews: list[DecisionReview] | None = None,
) -> tuple[DecisionReviewService, ReviewRepo]:
    repository = ReviewRepo(reviews)
    return (
        DecisionReviewService(
            repository,
            DecisionRepo(decisions),
            AcceptanceRepo(acceptances),
            OutcomeRepo(outcomes),
        ),
        repository,
    )


def valid_graph() -> tuple[Decision, DecisionAcceptance, list[DecisionOutcome]]:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    outcomes = [make_outcome(decision.id, acceptance.id)]
    return decision, acceptance, outcomes


def test_add_validates_relations_then_saves_complete_review() -> None:
    decision, acceptance, outcomes = valid_graph()
    second = make_outcome(
        decision.id,
        acceptance.id,
        idempotency_key="outcome-2",
        validated_at=_T_OUTCOME_VALIDATED_LATER,
    )
    service, repository = make_service([decision], [acceptance], [*outcomes, second])

    review = service.add(**add_values(decision, acceptance, [second, *outcomes]))  # type: ignore[arg-type]

    assert repository.save_calls == [review]
    assert review.outcome_ids == (second.id, outcomes[0].id)
    assert service.show(review.id) == review


def test_local_validation_happens_before_repository_reads_or_writes() -> None:
    decision, acceptance, outcomes = valid_graph()
    service, repository = make_service([decision], [acceptance], outcomes)
    values = add_values(decision, acceptance, outcomes)
    values["findings"] = []
    with pytest.raises(ValidationError):
        service.add(**values)  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_missing_decision_or_acceptance_never_writes() -> None:
    decision, acceptance, outcomes = valid_graph()
    service, repository = make_service([], [acceptance], outcomes)
    with pytest.raises(DecisionReviewDecisionNotFoundError):
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]
    assert repository.save_calls == []

    service, repository = make_service([decision], [], outcomes)
    with pytest.raises(DecisionReviewAcceptanceNotFoundError):
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_acceptance_for_another_decision_never_writes() -> None:
    decision, _, outcomes = valid_graph()
    other = make_decision(idempotency_key="other")
    acceptance = make_acceptance(other.id)
    service, repository = make_service([decision, other], [acceptance], outcomes)
    with pytest.raises(DecisionReviewAcceptanceMismatchError):
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_missing_or_wrong_outcome_relations_never_write() -> None:
    decision, acceptance, outcomes = valid_graph()
    service, repository = make_service([decision], [acceptance], [])
    with pytest.raises(DecisionReviewOutcomeNotFoundError):
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]
    assert repository.save_calls == []

    other_decision = make_decision(idempotency_key="other")
    wrong_decision = make_outcome(other_decision.id, acceptance.id)
    service, repository = make_service([decision, other_decision], [acceptance], [wrong_decision])
    with pytest.raises(DecisionReviewOutcomeDecisionMismatchError):
        service.add(**add_values(decision, acceptance, [wrong_decision]))  # type: ignore[arg-type]
    assert repository.save_calls == []

    other_acceptance = make_acceptance(decision.id, idempotency_key="other-acceptance")
    wrong_acceptance = make_outcome(decision.id, other_acceptance.id)
    service, repository = make_service(
        [decision], [acceptance, other_acceptance], [wrong_acceptance]
    )
    with pytest.raises(DecisionReviewOutcomeAcceptanceMismatchError):
        service.add(**add_values(decision, acceptance, [wrong_acceptance]))  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_review_time_must_follow_every_linked_outcome() -> None:
    decision, acceptance, outcomes = valid_graph()
    later = make_outcome(
        decision.id,
        acceptance.id,
        idempotency_key="later",
        validated_at=_T_OUTCOME_VALIDATED_TOO_LATE,
    )
    service, repository = make_service([decision], [acceptance], [*outcomes, later])
    with pytest.raises(DecisionReviewBeforeOutcomeError):
        service.add(**add_values(decision, acceptance, [*outcomes, later]))  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_equivalent_replay_ignores_generated_and_evidence_capture_times() -> None:
    decision, acceptance, outcomes = valid_graph()
    service, repository = make_service([decision], [acceptance], outcomes)
    values = add_values(decision, acceptance, outcomes)
    existing = service.add(**values)  # type: ignore[arg-type]
    values["evidence_references"] = [
        EvidenceReference(
            kind="review",
            locator="review:1",
            captured_at=datetime(2026, 7, 18, 13, 0, tzinfo=UTC),
        )
    ]

    assert service.add(**values) is existing  # type: ignore[arg-type]
    assert repository.save_calls == [existing]


def test_conflicting_key_fails_and_different_key_appends_review() -> None:
    decision, acceptance, outcomes = valid_graph()
    service, repository = make_service([decision], [acceptance], outcomes)
    values = add_values(decision, acceptance, outcomes)
    first = service.add(**values)  # type: ignore[arg-type]
    values["summary"] = "A conflicting interpretation."
    with pytest.raises(DecisionReviewIdempotencyConflictError):
        service.add(**values)  # type: ignore[arg-type]
    assert repository.save_calls == [first]

    values["idempotency_key"] = "review-2"
    second = service.add(**values)  # type: ignore[arg-type]
    assert repository.save_calls == [first, second]
    assert first.outcome_ids == second.outcome_ids


def test_history_is_chronological_independent_of_repository_order() -> None:
    decision, acceptance, outcomes = valid_graph()
    values = add_values(decision, acceptance, outcomes)
    values["recorded_at"] = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    values["reviewed_at"] = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    earlier = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "reviewed_at": datetime(2026, 7, 18, 11, 0, tzinfo=UTC),
        }
    )
    tied_low = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-000000000001"),
            "idempotency_key": "review-2",
        }
    )
    tied_high = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            "idempotency_key": "review-3",
        }
    )
    service, _ = make_service([decision], [acceptance], outcomes, [tied_high, tied_low, earlier])

    assert service.list_for_decision(decision.id) == [earlier, tied_low, tied_high]


def test_empty_history_and_missing_review_are_controlled() -> None:
    decision = make_decision()
    service, _ = make_service([decision], [], [])
    assert service.list_for_decision(decision.id) == []
    with pytest.raises(DecisionReviewNotFoundError):
        service.show(UUID("99999999-9999-9999-9999-999999999999"))


@pytest.mark.parametrize("operation", ["list", "show"])
def test_persisted_relation_corruption_fails_closed(operation: str) -> None:
    decision, acceptance, outcomes = valid_graph()
    values = add_values(decision, acceptance, outcomes)
    values["recorded_at"] = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    review = DecisionReview.model_validate(values)
    service, _ = make_service([decision], [acceptance], [], [review])

    with pytest.raises(DecisionReviewOutcomeNotFoundError):
        if operation == "list":
            service.list_for_decision(decision.id)
        else:
            service.show(review.id)


def test_duplicate_idempotency_key_raises_ambiguity_error() -> None:
    decision, acceptance, outcomes = valid_graph()
    values = add_values(decision, acceptance, outcomes)
    first = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000a1"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    second = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000a2"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    service, repository = make_service([decision], [acceptance], outcomes, [first, second])

    with pytest.raises(DecisionReviewIdempotencyAmbiguityError) as exc:
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]

    assert exc.value.decision_id == decision.id
    assert exc.value.idempotency_key == "review-1"
    assert exc.value.match_count == 2


def test_ambiguity_never_calls_save() -> None:
    decision, acceptance, outcomes = valid_graph()
    values = add_values(decision, acceptance, outcomes)
    first = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000b1"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    second = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000b2"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    service, repository = make_service([decision], [acceptance], outcomes, [first, second])

    with pytest.raises(DecisionReviewIdempotencyAmbiguityError):
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]

    assert repository.save_calls == []


def test_ambiguity_is_order_independent() -> None:
    decision, acceptance, outcomes = valid_graph()
    values = add_values(decision, acceptance, outcomes)
    review_a = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000c1"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    review_b = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000c2"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )

    forward_service, _ = make_service([decision], [acceptance], outcomes, [review_a, review_b])
    reversed_service, _ = make_service([decision], [acceptance], outcomes, [review_b, review_a])

    with pytest.raises(DecisionReviewIdempotencyAmbiguityError) as exc_forward:
        forward_service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]

    with pytest.raises(DecisionReviewIdempotencyAmbiguityError) as exc_reversed:
        reversed_service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]

    assert exc_reversed.value.decision_id == exc_forward.value.decision_id
    assert exc_reversed.value.idempotency_key == exc_forward.value.idempotency_key
    assert exc_reversed.value.match_count == exc_forward.value.match_count
    assert str(exc_reversed.value) == str(exc_forward.value)


def test_semantically_equivalent_duplicates_also_ambiguous() -> None:
    decision, acceptance, outcomes = valid_graph()
    values = add_values(decision, acceptance, outcomes)
    first = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000d1"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    second = DecisionReview.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000d2"),
            "recorded_at": _T_REVIEW_RECORDED,
        }
    )
    service, repository = make_service([decision], [acceptance], outcomes, [first, second])

    with pytest.raises(DecisionReviewIdempotencyAmbiguityError) as exc:
        service.add(**add_values(decision, acceptance, outcomes))  # type: ignore[arg-type]

    assert exc.value.match_count == 2
    assert repository.save_calls == []
