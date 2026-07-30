from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.core.paths import resolve_neural_paths
from neural_engine.domain import (
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    EvidenceReference,
)
from neural_engine.infrastructure.json_decision_review_repository import (
    JsonDecisionReviewRepository,
)


def make_review(review_id: UUID) -> DecisionReview:
    return DecisionReview(
        id=review_id,
        recorded_at=datetime(2026, 7, 18, 14, 0, tzinfo=UTC),
        decision_id=UUID("11111111-1111-1111-1111-111111111111"),
        acceptance_id=UUID("22222222-2222-2222-2222-222222222222"),
        outcome_ids=(
            UUID("44444444-4444-4444-4444-444444444444"),
            UUID("33333333-3333-3333-3333-333333333333"),
        ),
        reviewed_by="owner",
        reviewed_at=datetime(2026, 7, 18, 13, 0, tzinfo=UTC),
        assessment=DecisionReviewAssessment.MIXED,
        summary="The decision was partly sound.",
        findings=("First finding.", "Second finding."),
        candidate_lessons=("Validate earlier.", "Retain explicit evidence."),
        evidence_references=(EvidenceReference(kind="review", locator="review:1"),),
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="review-repository",
        tags=("architecture",),
    )


def test_save_load_and_get_preserve_complete_ordered_record(tmp_path: Path) -> None:
    repository = JsonDecisionReviewRepository(tmp_path)
    review = make_review(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    repository.save(review)

    assert repository.load_all() == [review]
    assert repository.get_by_id(review.id) == review
    restored = repository.load_all()[0]
    assert restored.outcome_ids == review.outcome_ids
    assert restored.findings == review.findings
    assert restored.candidate_lessons == review.candidate_lessons
    payload = (tmp_path / f"{review.id}.json").read_text(encoding="utf-8")
    assert payload.index('"acceptance_id"') < payload.index('"assessment"')


def test_load_all_uses_deterministic_file_order(tmp_path: Path) -> None:
    repository = JsonDecisionReviewRepository(tmp_path)
    high = make_review(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    low = make_review(UUID("00000000-0000-0000-0000-000000000001"))
    repository.save(high)
    repository.save(low)
    assert repository.load_all() == [low, high]


def test_missing_directory_or_id_is_controlled(tmp_path: Path) -> None:
    repository = JsonDecisionReviewRepository(tmp_path / "missing")
    assert repository.load_all() == []
    assert repository.get_by_id(UUID("11111111-1111-1111-1111-111111111111")) is None


def test_malformed_persisted_data_fails_without_repair(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text('{"assessment":"sound"}', encoding="utf-8")
    with pytest.raises(ValidationError):
        JsonDecisionReviewRepository(tmp_path).load_all()
    assert (tmp_path / "broken.json").read_text(encoding="utf-8") == '{"assessment":"sound"}'


def test_default_path_uses_decision_reviews_constant() -> None:
    assert JsonDecisionReviewRepository()._directory == resolve_neural_paths().DECISION_REVIEWS
