from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.application.decision_review_service import DecisionReviewNotFoundError
from neural_engine.application.experience_service import (
    DecisionReviewPromotionIdempotencyAmbiguityError,
    DecisionReviewPromotionIdempotencyConflictError,
    DecisionReviewPromotionSelector,
    DecisionReviewPromotionSourceIndexError,
    DecisionReviewPromotionSourceTextMismatchError,
    ExperienceService,
    ObservationNotFoundError,
)
from neural_engine.domain import (
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    DecisionReviewPromotion,
    DecisionReviewPromotionSourceKind,
    DecisionReviewPromotionSourceStatement,
    Experience,
    ExperienceResult,
    Observation,
)
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.observation_repository import ObservationRepository

REVIEW_ID = UUID("11111111-1111-1111-1111-111111111111")
EXPERIENCE_ID = UUID("22222222-2222-2222-2222-222222222222")
T_REVIEW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
T_RECORDED = datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
T_EXPERIENCE = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)


class FakeExperienceRepository(ExperienceRepository):
    def __init__(self, experiences: list[Experience] | None = None) -> None:
        self.experiences = list(experiences or [])
        self.save_calls: list[Experience] = []

    def save(self, experience: Experience) -> None:
        self.save_calls.append(experience)
        self.experiences.append(experience)

    def load_all(self) -> list[Experience]:
        return list(self.experiences)

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        return next((item for item in self.experiences if item.id == experience_id), None)


class FakeObservationRepository(ObservationRepository):
    def __init__(self, observations: list[Observation] | None = None) -> None:
        self.observations = list(observations or [])

    def save(self, observation: Observation) -> None:
        self.observations.append(observation)

    def load_all(self) -> list[Observation]:
        return list(self.observations)

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        return next((item for item in self.observations if item.id == observation_id), None)


class FakeDecisionReviewReader:
    def __init__(self, review: DecisionReview | None) -> None:
        self.review = review
        self.show_calls: list[UUID] = []

    def show(self, review_id: UUID) -> DecisionReview:
        self.show_calls.append(review_id)
        if self.review is None or self.review.id != review_id:
            raise DecisionReviewNotFoundError(review_id)
        return self.review


def make_review() -> DecisionReview:
    return DecisionReview(
        id=REVIEW_ID,
        recorded_at=T_RECORDED,
        decision_id=UUID("33333333-3333-3333-3333-333333333333"),
        acceptance_id=UUID("44444444-4444-4444-4444-444444444444"),
        outcome_ids=(UUID("55555555-5555-5555-5555-555555555555"),),
        reviewed_by="reviewer",
        reviewed_at=T_REVIEW,
        assessment=DecisionReviewAssessment.MIXED,
        summary="Reviewed result.",
        findings=("Keep the boundary explicit.", "Validate persisted provenance."),
        candidate_lessons=("Promote only with authority.", "Keep learning append-only."),
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="review-key",
    )


def selector(
    kind: DecisionReviewPromotionSourceKind = DecisionReviewPromotionSourceKind.FINDING,
    index: int = 0,
) -> DecisionReviewPromotionSelector:
    return DecisionReviewPromotionSelector(kind=kind, index=index)


def add_values(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "decision_review_id": REVIEW_ID,
        "source_selectors": [selector()],
        "promoted_by": "learning-owner",
        "promotion_reason": "The reviewed finding is operationally reusable.",
        "idempotency_key": "promotion-1",
        "title": "Explicit promotion",
        "context": "Decision review follow-up",
        "action": "Promoted one reviewed statement",
        "outcome": "Experience recorded with provenance",
        "result": ExperienceResult.SUCCESS,
        "tags": ["decision", "learning"],
    }
    values.update(updates)
    return values


def make_service(
    experiences: list[Experience] | None = None,
    review: DecisionReview | None = None,
    observations: list[Observation] | None = None,
) -> tuple[ExperienceService, FakeExperienceRepository, FakeDecisionReviewReader]:
    repository = FakeExperienceRepository(experiences)
    reader = FakeDecisionReviewReader(review if review is not None else make_review())
    return (
        ExperienceService(repository, FakeObservationRepository(observations), reader),
        repository,
        reader,
    )


def promoted_experience(**updates: object) -> Experience:
    values: dict[str, object] = {
        "id": EXPERIENCE_ID,
        "timestamp": T_EXPERIENCE,
        "title": "Explicit promotion",
        "context": "Decision review follow-up",
        "action": "Promoted one reviewed statement",
        "outcome": "Experience recorded with provenance",
        "result": ExperienceResult.SUCCESS,
        "tags": ["decision", "learning"],
        "decision_review_promotion": DecisionReviewPromotion(
            decision_review_id=REVIEW_ID,
            source_statements=(
                DecisionReviewPromotionSourceStatement(
                    kind=DecisionReviewPromotionSourceKind.FINDING,
                    index=0,
                    text="Keep the boundary explicit.",
                ),
            ),
            promoted_by="learning-owner",
            promotion_reason="The reviewed finding is operationally reusable.",
            idempotency_key="promotion-1",
        ),
    }
    values.update(updates)
    return Experience.model_validate(values)


def test_plain_experience_has_no_promotion_provenance() -> None:
    experience = Experience(
        title="Plain",
        context="Direct",
        action="Record",
        outcome="Stored",
        result=ExperienceResult.SUCCESS,
    )

    assert experience.decision_review_promotion is None
    with pytest.raises(ValidationError):
        experience.decision_review_promotion = DecisionReviewPromotion(
            decision_review_id=REVIEW_ID,
            source_statements=(
                DecisionReviewPromotionSourceStatement(
                    kind=DecisionReviewPromotionSourceKind.FINDING,
                    index=0,
                    text="Text",
                ),
            ),
            promoted_by="owner",
            promotion_reason="reason",
            idempotency_key="key",
        )


def test_durable_promotion_schema_contains_only_authorized_fields() -> None:
    assert set(DecisionReviewPromotion.model_fields) == {
        "decision_review_id",
        "source_statements",
        "promoted_by",
        "promotion_reason",
        "idempotency_key",
    }
    assert set(DecisionReviewPromotionSourceStatement.model_fields) == {
        "kind",
        "index",
        "text",
    }


def test_promotion_values_are_immutable_ordered_and_serialize_deterministically() -> None:
    promotion = DecisionReviewPromotion(
        decision_review_id=REVIEW_ID,
        source_statements=(
            DecisionReviewPromotionSourceStatement(
                kind=DecisionReviewPromotionSourceKind.FINDING,
                index=1,
                text=" Finding two ",
            ),
            DecisionReviewPromotionSourceStatement(
                kind=DecisionReviewPromotionSourceKind.CANDIDATE_LESSON,
                index=0,
                text="Candidate one",
            ),
        ),
        promoted_by=" owner ",
        promotion_reason=" because ",
        idempotency_key=" key ",
    )

    assert [item.kind.value for item in promotion.source_statements] == [
        "finding",
        "candidate_lesson",
    ]
    assert promotion.source_statements[0].text == "Finding two"
    assert promotion.model_dump(mode="json")["source_statements"] == [
        {"kind": "finding", "index": 1, "text": "Finding two"},
        {"kind": "candidate_lesson", "index": 0, "text": "Candidate one"},
    ]
    with pytest.raises(ValidationError):
        promotion.promoted_by = "different"
    with pytest.raises(ValidationError):
        promotion.source_statements[0].text = "different"


@pytest.mark.parametrize("kind", ["finding", "candidate_lesson"])
def test_exact_source_kind_vocabulary(kind: str) -> None:
    statement = DecisionReviewPromotionSourceStatement.model_validate(
        {"kind": kind, "index": 0, "text": "Text"}
    )
    assert statement.kind.value == kind


@pytest.mark.parametrize("kind", ["lesson", "candidate-lesson", "Finding"])
def test_source_kind_rejects_non_contract_values(kind: str) -> None:
    with pytest.raises(ValidationError):
        DecisionReviewPromotionSourceStatement.model_validate(
            {"kind": kind, "index": 0, "text": "Text"}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("promoted_by", " "),
        ("promotion_reason", " "),
        ("idempotency_key", " "),
        ("promoted_by", "x" * 256),
        ("promotion_reason", "x" * 1001),
        ("idempotency_key", "x" * 256),
    ],
)
def test_promotion_required_text_is_trimmed_and_bounded(field: str, value: str) -> None:
    values: dict[str, object] = {
        "decision_review_id": REVIEW_ID,
        "source_statements": [{"kind": "finding", "index": 0, "text": "Text"}],
        "promoted_by": "owner",
        "promotion_reason": "reason",
        "idempotency_key": "key",
    }
    values[field] = value
    with pytest.raises(ValidationError):
        DecisionReviewPromotion.model_validate(values)


@pytest.mark.parametrize("text", [" ", "x" * 1001])
def test_promotion_source_text_is_required_and_bounded(text: str) -> None:
    with pytest.raises(ValidationError):
        DecisionReviewPromotionSourceStatement(
            kind=DecisionReviewPromotionSourceKind.FINDING,
            index=0,
            text=text,
        )


def test_promotion_rejects_empty_duplicate_and_negative_sources() -> None:
    base = {
        "decision_review_id": REVIEW_ID,
        "promoted_by": "owner",
        "promotion_reason": "reason",
        "idempotency_key": "key",
    }
    with pytest.raises(ValidationError):
        DecisionReviewPromotion.model_validate({**base, "source_statements": []})
    with pytest.raises(ValidationError):
        DecisionReviewPromotion.model_validate(
            {
                **base,
                "source_statements": [
                    {"kind": "finding", "index": 0, "text": "First"},
                    {"kind": "finding", "index": 0, "text": "Second"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        DecisionReviewPromotionSourceStatement(
            kind=DecisionReviewPromotionSourceKind.FINDING, index=-1, text="Text"
        )


def test_selector_rejects_invalid_kind_and_duplicate_selection_before_review_read() -> None:
    with pytest.raises(ValueError, match="kind must be"):
        DecisionReviewPromotionSelector(
            kind=cast(DecisionReviewPromotionSourceKind, "lesson"), index=0
        )

    service, repository, reader = make_service()
    with pytest.raises(ValueError, match="must be unique"):
        service.add_from_decision_review(
            **add_values(source_selectors=[selector(), selector()])  # type: ignore[arg-type]
        )
    assert reader.show_calls == []
    assert repository.save_calls == []


def test_invalid_promotion_authority_fails_before_review_read() -> None:
    service, repository, reader = make_service()

    with pytest.raises(ValueError, match="promoted_by must not be blank"):
        service.add_from_decision_review(
            **add_values(promoted_by=" ")  # type: ignore[arg-type]
        )

    assert reader.show_calls == []
    assert repository.save_calls == []


def test_add_from_review_preserves_order_and_copies_exact_review_text() -> None:
    service, repository, reader = make_service()
    experience = service.add_from_decision_review(
        **add_values(
            source_selectors=[
                selector(DecisionReviewPromotionSourceKind.CANDIDATE_LESSON, 1),
                selector(DecisionReviewPromotionSourceKind.FINDING, 0),
                selector(DecisionReviewPromotionSourceKind.CANDIDATE_LESSON, 0),
            ]
        )  # type: ignore[arg-type]
    )

    promotion = experience.decision_review_promotion
    assert promotion is not None
    assert [(item.kind.value, item.index, item.text) for item in promotion.source_statements] == [
        ("candidate_lesson", 1, "Keep learning append-only."),
        ("finding", 0, "Keep the boundary explicit."),
        ("candidate_lesson", 0, "Promote only with authority."),
    ]
    assert repository.save_calls == [experience]
    assert reader.show_calls == [REVIEW_ID]


def test_missing_review_and_invalid_index_fail_without_writing() -> None:
    repository = FakeExperienceRepository()
    missing_reader = FakeDecisionReviewReader(None)
    missing_service = ExperienceService(repository, FakeObservationRepository(), missing_reader)
    with pytest.raises(DecisionReviewNotFoundError):
        missing_service.add_from_decision_review(**add_values())  # type: ignore[arg-type]

    service, repository, _ = make_service()
    with pytest.raises(DecisionReviewPromotionSourceIndexError):
        service.add_from_decision_review(
            **add_values(source_selectors=[selector(index=99)])  # type: ignore[arg-type]
        )
    assert repository.save_calls == []


def test_optional_observation_validation_remains_enforced() -> None:
    missing_id = UUID("99999999-9999-9999-9999-999999999999")
    service, repository, _ = make_service()
    with pytest.raises(ObservationNotFoundError):
        service.add_from_decision_review(
            **add_values(observation_ids=[missing_id])  # type: ignore[arg-type]
        )
    assert repository.save_calls == []


def test_equivalent_replay_returns_original_identity_and_does_not_write() -> None:
    existing = promoted_experience()
    service, repository, _ = make_service([existing])

    replay = service.add_from_decision_review(**add_values())  # type: ignore[arg-type]

    assert replay is existing
    assert replay.id == EXPERIENCE_ID
    assert replay.timestamp == T_EXPERIENCE
    assert repository.save_calls == []


def test_conflicting_reuse_and_ambiguity_fail_without_writing() -> None:
    existing = promoted_experience()
    service, repository, _ = make_service([existing])
    with pytest.raises(DecisionReviewPromotionIdempotencyConflictError):
        service.add_from_decision_review(
            **add_values(title="Conflicting title")  # type: ignore[arg-type]
        )
    assert repository.save_calls == []

    duplicate = promoted_experience(id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    for records in ([existing, duplicate], [duplicate, existing]):
        service, repository, _ = make_service(records)
        with pytest.raises(DecisionReviewPromotionIdempotencyAmbiguityError) as error:
            service.add_from_decision_review(**add_values())  # type: ignore[arg-type]
        assert error.value.match_count == 2
        assert repository.save_calls == []


def test_different_keys_allow_multiple_experiences_from_one_review() -> None:
    existing = promoted_experience()
    service, repository, _ = make_service([existing])
    added = service.add_from_decision_review(
        **add_values(idempotency_key="promotion-2")  # type: ignore[arg-type]
    )

    assert added.id != existing.id
    assert added.decision_review_promotion is not None
    assert added.decision_review_promotion.decision_review_id == REVIEW_ID
    assert repository.save_calls == [added]


@pytest.mark.parametrize("operation", ["replay", "get", "list", "observation_list"])
def test_tampered_persisted_source_text_fails_closed_on_replay_and_reads(operation: str) -> None:
    promotion = promoted_experience().decision_review_promotion
    assert promotion is not None
    tampered = promoted_experience(
        observation_ids=[UUID("77777777-7777-7777-7777-777777777777")],
        decision_review_promotion=promotion.model_copy(
            update={
                "source_statements": (
                    promotion.source_statements[0].model_copy(update={"text": "Tampered"}),
                )
            }
        ),
    )
    observation = Observation(id=UUID("77777777-7777-7777-7777-777777777777"), content="Context")
    service, repository, _ = make_service([tampered], observations=[observation])

    with pytest.raises(DecisionReviewPromotionSourceTextMismatchError):
        if operation == "replay":
            service.add_from_decision_review(
                **add_values(observation_ids=[observation.id])  # type: ignore[arg-type]
            )
        elif operation == "get":
            service.get_by_id(tampered.id)
        elif operation == "list":
            service.list_experiences()
        else:
            service.list_for_observation(observation.id)
    assert repository.save_calls == []


def test_persisted_out_of_range_source_index_fails_closed_on_read() -> None:
    promotion = promoted_experience().decision_review_promotion
    assert promotion is not None
    malformed = promoted_experience(
        decision_review_promotion=promotion.model_copy(
            update={
                "source_statements": (
                    promotion.source_statements[0].model_copy(update={"index": 99}),
                )
            }
        )
    )
    service, repository, _ = make_service([malformed])

    with pytest.raises(DecisionReviewPromotionSourceIndexError):
        service.get_by_id(malformed.id)
    assert repository.save_calls == []


def test_existing_direct_and_observation_creation_remain_plain() -> None:
    observation = Observation(content="Source content")
    service, repository, _ = make_service(observations=[observation])

    direct = service.add(
        title="Direct",
        context="Caller context",
        action="Record",
        outcome="Stored",
        result=ExperienceResult.SUCCESS,
    )
    derived = service.add_from_observation(
        observation_id=observation.id,
        title="Derived",
        action="Promote observation",
        outcome="Stored",
        result=ExperienceResult.MIXED,
    )

    assert direct.decision_review_promotion is None
    assert derived.decision_review_promotion is None
    assert repository.save_calls == [direct, derived]
