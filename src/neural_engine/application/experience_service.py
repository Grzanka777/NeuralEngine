from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from neural_engine.domain import (
    DecisionReview,
    DecisionReviewPromotion,
    DecisionReviewPromotionSourceKind,
    DecisionReviewPromotionSourceStatement,
    Experience,
    ExperienceResult,
)
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.observation_repository import ObservationRepository


class ObservationNotFoundError(Exception):
    """Raised when an experience references an unknown observation."""

    def __init__(self, observation_id: UUID) -> None:
        self.observation_id = observation_id
        super().__init__(f"Observation not found: {observation_id}")


class DecisionReviewReader(Protocol):
    """The existing validated DecisionReview application read boundary."""

    def show(self, review_id: UUID) -> DecisionReview: ...


@dataclass(frozen=True, slots=True)
class DecisionReviewPromotionSelector:
    """A caller-selected zero-based position in one DecisionReview collection."""

    kind: DecisionReviewPromotionSourceKind
    index: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DecisionReviewPromotionSourceKind):
            raise ValueError(
                "Decision review promotion selector kind must be finding or candidate_lesson."
            )
        if self.index < 0:
            raise ValueError("Decision review promotion selector index must not be negative.")


class DecisionReviewPromotionError(Exception):
    """Base error for DecisionReview-to-Experience promotion failures."""


class DecisionReviewPromotionSourcesRequiredError(DecisionReviewPromotionError):
    def __init__(self) -> None:
        super().__init__("Decision review promotion requires at least one source selector.")


class DecisionReviewPromotionSourceIndexError(DecisionReviewPromotionError):
    def __init__(
        self,
        review_id: UUID,
        kind: DecisionReviewPromotionSourceKind,
        index: int,
    ) -> None:
        self.review_id = review_id
        self.kind = kind
        self.index = index
        super().__init__(
            f"Decision review {review_id} has no {kind.value} at zero-based index {index}."
        )


class DecisionReviewPromotionSourceTextMismatchError(DecisionReviewPromotionError):
    def __init__(
        self,
        experience_id: UUID,
        kind: DecisionReviewPromotionSourceKind,
        index: int,
    ) -> None:
        self.experience_id = experience_id
        self.kind = kind
        self.index = index
        super().__init__(
            f"Experience {experience_id} has promotion source text that does not match "
            f"DecisionReview {kind.value} at zero-based index {index}."
        )


class DecisionReviewPromotionIdempotencyConflictError(DecisionReviewPromotionError):
    def __init__(self, review_id: UUID, idempotency_key: str) -> None:
        self.review_id = review_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Decision review Experience promotion idempotency key {idempotency_key!r} already "
            f"exists for DecisionReview {review_id} with a different payload."
        )


class DecisionReviewPromotionIdempotencyAmbiguityError(DecisionReviewPromotionError):
    def __init__(self, review_id: UUID, idempotency_key: str, match_count: int) -> None:
        self.review_id = review_id
        self.idempotency_key = idempotency_key
        self.match_count = match_count
        super().__init__(
            f"Decision review Experience promotion idempotency key {idempotency_key!r} is "
            f"ambiguous for DecisionReview {review_id}: {match_count} persisted Experiences "
            "share the same key."
        )


class ExperienceService:
    """Application service for experiences."""

    def __init__(
        self,
        experience_repository: ExperienceRepository,
        observation_repository: ObservationRepository,
        decision_review_service: DecisionReviewReader,
    ) -> None:
        self._experience_repository = experience_repository
        self._observation_repository = observation_repository
        self._decision_review_service = decision_review_service

    def add(
        self,
        title: str,
        context: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        observation_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
    ) -> Experience:
        validated_observation_ids = observation_ids or []
        self._validate_observation_ids(validated_observation_ids)

        experience = Experience(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=validated_observation_ids,
            tags=tags or [],
        )

        self._experience_repository.save(experience)

        return experience

    def add_from_observation(
        self,
        observation_id: UUID,
        title: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        tags: list[str] | None = None,
    ) -> Experience:
        observation = self._observation_repository.get_by_id(observation_id)

        if observation is None:
            raise ObservationNotFoundError(observation_id)

        experience = Experience(
            title=title,
            context=observation.content,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=[observation.id],
            tags=tags or [],
        )

        self._experience_repository.save(experience)

        return experience

    def add_from_decision_review(
        self,
        decision_review_id: UUID,
        source_selectors: list[DecisionReviewPromotionSelector],
        promoted_by: str,
        promotion_reason: str,
        idempotency_key: str,
        title: str,
        context: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        observation_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
    ) -> Experience:
        self._validate_source_selectors(source_selectors)
        promoted_by, promotion_reason, idempotency_key = DecisionReviewPromotion.normalize_metadata(
            promoted_by, promotion_reason, idempotency_key
        )

        review = self._decision_review_service.show(decision_review_id)
        source_statements = self._copy_source_statements(review, source_selectors)
        validated_observation_ids = observation_ids or []
        self._validate_observation_ids(validated_observation_ids)
        candidate = Experience(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=validated_observation_ids,
            tags=tags or [],
            decision_review_promotion=DecisionReviewPromotion(
                decision_review_id=review.id,
                source_statements=source_statements,
                promoted_by=promoted_by,
                promotion_reason=promotion_reason,
                idempotency_key=idempotency_key,
            ),
        )

        existing = self._find_promotion_by_idempotency_key(
            self._experience_repository.load_all(), candidate
        )
        if existing is not None:
            self._validate_promotion_integrity(existing)
            if self._semantic_payload(existing) == self._semantic_payload(candidate):
                return existing
            promotion = candidate.decision_review_promotion
            assert promotion is not None
            raise DecisionReviewPromotionIdempotencyConflictError(
                promotion.decision_review_id, promotion.idempotency_key
            )

        self._experience_repository.save(candidate)
        return candidate

    def list_experiences(self) -> list[Experience]:
        experiences = self._experience_repository.load_all()
        for experience in experiences:
            self._validate_promotion_integrity(experience)
        return experiences

    def list_for_observation(self, observation_id: UUID) -> list[Experience]:
        if self._observation_repository.get_by_id(observation_id) is None:
            raise ObservationNotFoundError(observation_id)

        experiences = self._experience_repository.load_all()

        linked = [
            experience for experience in experiences if observation_id in experience.observation_ids
        ]
        for experience in linked:
            self._validate_promotion_integrity(experience)
        return linked

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        experience = self._experience_repository.get_by_id(experience_id)
        if experience is not None:
            self._validate_promotion_integrity(experience)
        return experience

    def _validate_observation_ids(self, observation_ids: list[UUID]) -> None:
        for observation_id in observation_ids:
            if self._observation_repository.get_by_id(observation_id) is None:
                raise ObservationNotFoundError(observation_id)

    def _copy_source_statements(
        self,
        review: DecisionReview,
        selectors: list[DecisionReviewPromotionSelector],
    ) -> tuple[DecisionReviewPromotionSourceStatement, ...]:
        statements: list[DecisionReviewPromotionSourceStatement] = []
        for selector in selectors:
            values = self._review_values(review, selector.kind)
            try:
                text = values[selector.index]
            except IndexError as error:
                raise DecisionReviewPromotionSourceIndexError(
                    review.id, selector.kind, selector.index
                ) from error
            statements.append(
                DecisionReviewPromotionSourceStatement(
                    kind=selector.kind,
                    index=selector.index,
                    text=text,
                )
            )
        return tuple(statements)

    @staticmethod
    def _validate_source_selectors(
        selectors: list[DecisionReviewPromotionSelector],
    ) -> None:
        if not selectors:
            raise DecisionReviewPromotionSourcesRequiredError
        pairs = [(selector.kind, selector.index) for selector in selectors]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Decision review promotion source selectors must be unique.")

    def _validate_promotion_integrity(self, experience: Experience) -> None:
        promotion = experience.decision_review_promotion
        if promotion is None:
            return
        review = self._decision_review_service.show(promotion.decision_review_id)
        for statement in promotion.source_statements:
            values = self._review_values(review, statement.kind)
            try:
                expected_text = values[statement.index]
            except IndexError as error:
                raise DecisionReviewPromotionSourceIndexError(
                    review.id, statement.kind, statement.index
                ) from error
            if statement.text != expected_text:
                raise DecisionReviewPromotionSourceTextMismatchError(
                    experience.id, statement.kind, statement.index
                )

    @staticmethod
    def _review_values(
        review: DecisionReview, kind: DecisionReviewPromotionSourceKind
    ) -> tuple[str, ...]:
        if kind is DecisionReviewPromotionSourceKind.FINDING:
            return review.findings
        return review.candidate_lessons

    @staticmethod
    def _find_promotion_by_idempotency_key(
        experiences: list[Experience], candidate: Experience
    ) -> Experience | None:
        candidate_promotion = candidate.decision_review_promotion
        assert candidate_promotion is not None
        matches = [
            experience
            for experience in experiences
            if experience.decision_review_promotion is not None
            and experience.decision_review_promotion.decision_review_id
            == candidate_promotion.decision_review_id
            and experience.decision_review_promotion.idempotency_key
            == candidate_promotion.idempotency_key
        ]
        if len(matches) > 1:
            raise DecisionReviewPromotionIdempotencyAmbiguityError(
                candidate_promotion.decision_review_id,
                candidate_promotion.idempotency_key,
                len(matches),
            )
        return matches[0] if matches else None

    @staticmethod
    def _semantic_payload(experience: Experience) -> dict[str, object]:
        return experience.model_dump(mode="json", exclude={"id", "timestamp"})
