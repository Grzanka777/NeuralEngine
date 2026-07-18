from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import (
    DecisionOutcomeResult,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    EvidenceReference,
)
from neural_engine.domain.decision_review import (
    MAX_DECISION_REVIEW_CANDIDATE_LESSON_LENGTH,
    MAX_DECISION_REVIEW_CANDIDATE_LESSONS,
    MAX_DECISION_REVIEW_FINDING_LENGTH,
    MAX_DECISION_REVIEW_FINDINGS,
    MAX_DECISION_REVIEW_REVIEWER_LENGTH,
    MAX_DECISION_REVIEW_SUMMARY_LENGTH,
)


def review_values() -> dict[str, object]:
    return {
        "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "recorded_at": datetime(2026, 7, 18, 14, 0, tzinfo=UTC),
        "decision_id": UUID("11111111-1111-1111-1111-111111111111"),
        "acceptance_id": UUID("22222222-2222-2222-2222-222222222222"),
        "outcome_ids": [
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
        ],
        "reviewed_by": "  architecture-owner  ",
        "reviewed_at": datetime(2026, 7, 18, 15, 0, tzinfo=timezone(timedelta(hours=2))),
        "assessment": "inconclusive",
        "summary": "  Evidence needs another validation cycle.  ",
        "findings": ["  The result is environment-sensitive.  ", "More evidence is needed."],
        "candidate_lessons": ["  Validate on representative hardware.  "],
        "evidence_references": [
            EvidenceReference(kind="agent_review", locator="review:decision-review")
        ],
        "confidence": "medium",
        "idempotency_key": "  review-1  ",
        "tags": [" Architecture ", "architecture", "Review"],
    }


def test_constructs_normalized_immutable_review_with_deterministic_round_trip() -> None:
    review = DecisionReview.model_validate(review_values())
    restored = DecisionReview.model_validate_json(review.model_dump_json())

    assert restored == review
    assert review.reviewed_at == datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
    assert review.assessment is DecisionReviewAssessment.INCONCLUSIVE
    assert review.confidence is DecisionReviewConfidence.MEDIUM
    assert review.findings == (
        "The result is environment-sensitive.",
        "More evidence is needed.",
    )
    assert review.candidate_lessons == ("Validate on representative hardware.",)
    assert review.tags == ("Architecture", "Review")
    assert not hasattr(review, "action_ids")
    assert not hasattr(review, "status")
    with pytest.raises(ValidationError):
        review.summary = "changed"
    with pytest.raises(TypeError):
        review.findings[0] = "changed"  # type: ignore[index]


@pytest.mark.parametrize("field", ["id", "decision_id", "acceptance_id"])
def test_rejects_invalid_uuid_fields(field: str) -> None:
    values = review_values()
    values[field] = "not-a-uuid"
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)


@pytest.mark.parametrize("field", ["reviewed_by", "summary", "idempotency_key"])
def test_rejects_blank_required_text(field: str) -> None:
    values = review_values()
    values[field] = "  "
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)


def test_exact_assessment_and_confidence_vocabularies_are_separate_from_outcomes() -> None:
    assert {item.value for item in DecisionReviewAssessment} == {
        "sound",
        "flawed",
        "mixed",
        "inconclusive",
    }
    assert {item.value for item in DecisionReviewConfidence} == {"low", "medium", "high"}
    assert {item.value for item in DecisionOutcomeResult} == {
        "succeeded",
        "failed",
        "partial",
        "unknown",
    }
    values = review_values()
    values["assessment"] = "succeeded"
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)
    values = review_values()
    values["confidence"] = "certain"
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)


def test_requires_ordered_unique_outcome_ids() -> None:
    values = review_values()
    values["outcome_ids"] = []
    with pytest.raises(ValidationError, match="at least one outcome ID"):
        DecisionReview.model_validate(values)
    duplicate = UUID("33333333-3333-3333-3333-333333333333")
    values["outcome_ids"] = [duplicate, duplicate]
    with pytest.raises(ValidationError, match="outcome IDs must be unique"):
        DecisionReview.model_validate(values)


def test_requires_findings_and_allows_empty_candidate_lessons() -> None:
    values = review_values()
    values["findings"] = []
    with pytest.raises(ValidationError, match="at least one finding"):
        DecisionReview.model_validate(values)
    values = review_values()
    values["candidate_lessons"] = []
    assert DecisionReview.model_validate(values).candidate_lessons == ()


@pytest.mark.parametrize("field", ["findings", "candidate_lessons"])
def test_rejects_blank_or_case_insensitive_duplicate_ordered_text(field: str) -> None:
    values = review_values()
    values[field] = ["Finding", " finding "]
    with pytest.raises(ValidationError, match="must be unique"):
        DecisionReview.model_validate(values)
    values[field] = [" "]
    with pytest.raises(ValidationError, match="blank"):
        DecisionReview.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reviewed_by", "x" * (MAX_DECISION_REVIEW_REVIEWER_LENGTH + 1)),
        ("summary", "x" * (MAX_DECISION_REVIEW_SUMMARY_LENGTH + 1)),
        ("findings", ["x" * (MAX_DECISION_REVIEW_FINDING_LENGTH + 1)]),
        (
            "candidate_lessons",
            ["x" * (MAX_DECISION_REVIEW_CANDIDATE_LESSON_LENGTH + 1)],
        ),
        ("findings", [f"finding-{index}" for index in range(MAX_DECISION_REVIEW_FINDINGS + 1)]),
        (
            "candidate_lessons",
            [f"lesson-{index}" for index in range(MAX_DECISION_REVIEW_CANDIDATE_LESSONS + 1)],
        ),
    ],
)
def test_rejects_values_beyond_documented_bounds(field: str, value: object) -> None:
    values = review_values()
    values[field] = value
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)


@pytest.mark.parametrize("field", ["recorded_at", "reviewed_at"])
def test_rejects_naive_timestamps(field: str) -> None:
    values = review_values()
    values[field] = datetime(2026, 7, 18, 13, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        DecisionReview.model_validate(values)


def test_rejects_reviewed_at_later_than_recorded_at() -> None:
    values = review_values()
    values["reviewed_at"] = datetime(2026, 7, 18, 14, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="later than recorded_at"):
        DecisionReview.model_validate(values)


def test_evidence_and_tags_remain_immutable_and_validated() -> None:
    review = DecisionReview.model_validate(review_values())
    assert isinstance(review.evidence_references, tuple)
    assert isinstance(review.tags, tuple)
    values = review_values()
    values["evidence_references"] = [{"kind": "agent_review"}]
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)
    values = review_values()
    values["tags"] = [" "]
    with pytest.raises(ValidationError):
        DecisionReview.model_validate(values)
