from datetime import datetime
from uuid import UUID

from neural_engine.domain import (
    DecisionOutcome,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    EvidenceReference,
)
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
from neural_engine.ports.decision_repository import DecisionRepository
from neural_engine.ports.decision_review_repository import DecisionReviewRepository


class DecisionReviewError(Exception):
    """Base error for Decision review service failures."""


class DecisionReviewDecisionNotFoundError(DecisionReviewError):
    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision not found: {decision_id}")


class DecisionReviewAcceptanceNotFoundError(DecisionReviewError):
    def __init__(self, acceptance_id: UUID) -> None:
        self.acceptance_id = acceptance_id
        super().__init__(f"Decision acceptance not found: {acceptance_id}")


class DecisionReviewAcceptanceMismatchError(DecisionReviewError):
    def __init__(
        self, acceptance_id: UUID, expected_decision_id: UUID, actual_decision_id: UUID
    ) -> None:
        self.acceptance_id = acceptance_id
        self.expected_decision_id = expected_decision_id
        self.actual_decision_id = actual_decision_id
        super().__init__(
            f"Decision acceptance {acceptance_id} belongs to Decision {actual_decision_id}, "
            f"expected {expected_decision_id}."
        )


class DecisionReviewOutcomeNotFoundError(DecisionReviewError):
    def __init__(self, outcome_id: UUID) -> None:
        self.outcome_id = outcome_id
        super().__init__(f"Decision outcome not found: {outcome_id}")


class DecisionReviewOutcomeDecisionMismatchError(DecisionReviewError):
    def __init__(
        self, outcome_id: UUID, expected_decision_id: UUID, actual_decision_id: UUID
    ) -> None:
        self.outcome_id = outcome_id
        self.expected_decision_id = expected_decision_id
        self.actual_decision_id = actual_decision_id
        super().__init__(
            f"Decision outcome {outcome_id} belongs to Decision {actual_decision_id}, "
            f"expected {expected_decision_id}."
        )


class DecisionReviewOutcomeAcceptanceMismatchError(DecisionReviewError):
    def __init__(
        self, outcome_id: UUID, expected_acceptance_id: UUID, actual_acceptance_id: UUID
    ) -> None:
        self.outcome_id = outcome_id
        self.expected_acceptance_id = expected_acceptance_id
        self.actual_acceptance_id = actual_acceptance_id
        super().__init__(
            f"Decision outcome {outcome_id} references acceptance {actual_acceptance_id}, "
            f"expected {expected_acceptance_id}."
        )


class DecisionReviewBeforeOutcomeError(DecisionReviewError):
    def __init__(self, reviewed_at: datetime, latest_validated_at: datetime) -> None:
        self.reviewed_at = reviewed_at
        self.latest_validated_at = latest_validated_at
        super().__init__(
            f"Decision review reviewed_at {reviewed_at.isoformat()} precedes latest linked "
            f"outcome validation {latest_validated_at.isoformat()}."
        )


class DecisionReviewNotFoundError(DecisionReviewError):
    def __init__(self, review_id: UUID) -> None:
        self.review_id = review_id
        super().__init__(f"Decision review not found: {review_id}")


class DecisionReviewIdempotencyConflictError(DecisionReviewError):
    def __init__(self, decision_id: UUID, idempotency_key: str) -> None:
        self.decision_id = decision_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Decision review idempotency key {idempotency_key!r} already exists for "
            f"Decision {decision_id} with a different payload."
        )


class DecisionReviewIdempotencyAmbiguityError(DecisionReviewError):
    def __init__(self, decision_id: UUID, idempotency_key: str, match_count: int) -> None:
        self.decision_id = decision_id
        self.idempotency_key = idempotency_key
        self.match_count = match_count
        super().__init__(
            f"Decision review idempotency key {idempotency_key!r} is ambiguous for "
            f"Decision {decision_id}: {match_count} persisted reviews share the same key."
        )


class DecisionReviewService:
    """Application service for authorized interpretations of Decision outcomes."""

    def __init__(
        self,
        review_repository: DecisionReviewRepository,
        decision_repository: DecisionRepository,
        acceptance_repository: DecisionAcceptanceRepository,
        outcome_repository: DecisionOutcomeRepository,
    ) -> None:
        self._review_repository = review_repository
        self._decision_repository = decision_repository
        self._acceptance_repository = acceptance_repository
        self._outcome_repository = outcome_repository

    def add(
        self,
        decision_id: UUID,
        acceptance_id: UUID,
        outcome_ids: list[UUID],
        reviewed_by: str,
        reviewed_at: datetime,
        assessment: DecisionReviewAssessment,
        summary: str,
        findings: list[str],
        confidence: DecisionReviewConfidence,
        idempotency_key: str,
        candidate_lessons: list[str] | None = None,
        evidence_references: list[EvidenceReference] | None = None,
        tags: list[str] | None = None,
    ) -> DecisionReview:
        candidate = DecisionReview(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            outcome_ids=tuple(outcome_ids),
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            assessment=assessment,
            summary=summary,
            findings=tuple(findings),
            candidate_lessons=tuple(candidate_lessons or []),
            evidence_references=tuple(evidence_references or []),
            confidence=confidence,
            idempotency_key=idempotency_key,
            tags=tuple(tags or []),
        )

        self._require_decision(candidate.decision_id)
        self._validate_acceptance(candidate.acceptance_id, candidate.decision_id)
        outcomes = [
            self._load_and_validate_outcome(
                outcome_id, candidate.decision_id, candidate.acceptance_id
            )
            for outcome_id in candidate.outcome_ids
        ]
        self._validate_review_time(candidate.reviewed_at, outcomes)

        reviews = self._review_repository.load_all()
        existing = self._find_by_idempotency_key(reviews, candidate)
        if existing is not None:
            self._validate_review_relations(existing)
            if self._semantic_payload(existing) == self._semantic_payload(candidate):
                return existing
            raise DecisionReviewIdempotencyConflictError(
                candidate.decision_id, candidate.idempotency_key
            )

        self._review_repository.save(candidate)
        return candidate

    def list_for_decision(self, decision_id: UUID) -> list[DecisionReview]:
        self._require_decision(decision_id)
        reviews = [
            review
            for review in self._review_repository.load_all()
            if review.decision_id == decision_id
        ]
        for review in reviews:
            self._validate_review_relations(review)
        return sorted(reviews, key=lambda item: (item.reviewed_at, str(item.id)))

    def show(self, review_id: UUID) -> DecisionReview:
        review = self._review_repository.get_by_id(review_id)
        if review is None:
            raise DecisionReviewNotFoundError(review_id)
        self._validate_review_relations(review)
        return review

    def _require_decision(self, decision_id: UUID) -> None:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionReviewDecisionNotFoundError(decision_id)

    def _validate_acceptance(self, acceptance_id: UUID, decision_id: UUID) -> None:
        acceptance = self._acceptance_repository.get_by_id(acceptance_id)
        if acceptance is None:
            raise DecisionReviewAcceptanceNotFoundError(acceptance_id)
        if acceptance.decision_id != decision_id:
            raise DecisionReviewAcceptanceMismatchError(
                acceptance_id, decision_id, acceptance.decision_id
            )

    def _load_and_validate_outcome(
        self, outcome_id: UUID, decision_id: UUID, acceptance_id: UUID
    ) -> DecisionOutcome:
        outcome = self._outcome_repository.get_by_id(outcome_id)
        if outcome is None:
            raise DecisionReviewOutcomeNotFoundError(outcome_id)
        if outcome.decision_id != decision_id:
            raise DecisionReviewOutcomeDecisionMismatchError(
                outcome_id, decision_id, outcome.decision_id
            )
        if outcome.acceptance_id != acceptance_id:
            raise DecisionReviewOutcomeAcceptanceMismatchError(
                outcome_id, acceptance_id, outcome.acceptance_id
            )
        return outcome

    def _validate_review_relations(self, review: DecisionReview) -> None:
        self._require_decision(review.decision_id)
        self._validate_acceptance(review.acceptance_id, review.decision_id)
        outcomes = [
            self._load_and_validate_outcome(outcome_id, review.decision_id, review.acceptance_id)
            for outcome_id in review.outcome_ids
        ]
        self._validate_review_time(review.reviewed_at, outcomes)

    @staticmethod
    def _validate_review_time(reviewed_at: datetime, outcomes: list[DecisionOutcome]) -> None:
        latest_validated_at = max(outcome.validated_at for outcome in outcomes)
        if reviewed_at < latest_validated_at:
            raise DecisionReviewBeforeOutcomeError(reviewed_at, latest_validated_at)

    @staticmethod
    def _find_by_idempotency_key(
        reviews: list[DecisionReview], candidate: DecisionReview
    ) -> DecisionReview | None:
        matches = [
            review
            for review in reviews
            if review.decision_id == candidate.decision_id
            and review.idempotency_key == candidate.idempotency_key
        ]
        if len(matches) > 1:
            raise DecisionReviewIdempotencyAmbiguityError(
                candidate.decision_id, candidate.idempotency_key, len(matches)
            )
        return matches[0] if matches else None

    @staticmethod
    def _semantic_payload(review: DecisionReview) -> dict[str, object]:
        payload = review.model_dump(mode="json", exclude={"id", "recorded_at"})
        payload["evidence_references"] = [
            evidence.model_dump(mode="json", exclude={"captured_at"})
            for evidence in review.evidence_references
        ]
        return payload
