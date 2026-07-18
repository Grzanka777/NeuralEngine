from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.application.decision_review_service import (
    DecisionReviewDecisionNotFoundError,
    DecisionReviewNotFoundError,
    DecisionReviewService,
)
from neural_engine.application.experience_service import (
    DecisionReviewPromotionSelector,
    DecisionReviewPromotionSourceIndexError,
    DecisionReviewPromotionSourceTextMismatchError,
    ExperienceService,
)
from neural_engine.application.knowledge_service import KnowledgeService
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    DecisionReviewPromotion,
    DecisionReviewPromotionSourceKind,
    DecisionReviewPromotionSourceStatement,
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
)
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)
from neural_engine.infrastructure.json_decision_outcome_repository import (
    JsonDecisionOutcomeRepository,
)
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository
from neural_engine.infrastructure.json_decision_review_repository import (
    JsonDecisionReviewRepository,
)
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository

T_CREATED = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
T_ACCEPTED = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
T_OUTCOME = datetime(2026, 7, 18, 11, 0, tzinfo=UTC)
T_REVIEW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
T_RECORDED = datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
T_EXPERIENCE = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
T_KNOWLEDGE = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)


@dataclass
class RealBoundary:
    decision_repository: JsonDecisionRepository
    acceptance_repository: JsonDecisionAcceptanceRepository
    outcome_repository: JsonDecisionOutcomeRepository
    review_repository: JsonDecisionReviewRepository
    experience_repository: JsonExperienceRepository
    observation_repository: JsonObservationRepository
    knowledge_repository: JsonKnowledgeRepository
    experience_service: ExperienceService
    knowledge_service: KnowledgeService
    decision: Decision
    acceptance: DecisionAcceptance
    outcome: DecisionOutcome
    review: DecisionReview


def make_boundary(tmp_path: Path) -> RealBoundary:
    decision_repository = JsonDecisionRepository(tmp_path / "decisions")
    acceptance_repository = JsonDecisionAcceptanceRepository(tmp_path / "acceptances")
    outcome_repository = JsonDecisionOutcomeRepository(tmp_path / "outcomes")
    review_repository = JsonDecisionReviewRepository(tmp_path / "reviews")
    experience_repository = JsonExperienceRepository(tmp_path / "experiences")
    observation_repository = JsonObservationRepository(tmp_path / "observations")
    knowledge_repository = JsonKnowledgeRepository(tmp_path / "knowledge")

    decision = Decision(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        created_at=T_CREATED,
        project_key="NeuralEngine",
        title="Keep one validation owner",
        objective="Validate Experience provenance before Knowledge use",
        context_summary="Knowledge previously bypassed ExperienceService reads.",
        alternatives=("Use ExperienceService", "Duplicate validation"),
        proposed_option="Use ExperienceService",
        rationale="The existing service already owns promotion integrity.",
        proposed_by="architect",
        idempotency_key="knowledge-integrity-decision",
    )
    acceptance = DecisionAcceptance(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        accepted_at=T_ACCEPTED,
        decision_id=decision.id,
        accepted_by="owner",
        reason="Preserve one canonical boundary.",
        idempotency_key="knowledge-integrity-acceptance",
    )
    outcome = DecisionOutcome(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        recorded_at=T_RECORDED,
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        action_ids=(UUID("44444444-4444-4444-4444-444444444444"),),
        result=DecisionOutcomeResult.SUCCEEDED,
        summary="Validated boundary behavior.",
        validated_by="pytest",
        validated_at=T_OUTCOME,
        idempotency_key="knowledge-integrity-outcome",
    )
    review = DecisionReview(
        id=UUID("55555555-5555-5555-5555-555555555555"),
        recorded_at=T_RECORDED,
        decision_id=decision.id,
        acceptance_id=acceptance.id,
        outcome_ids=(outcome.id,),
        reviewed_by="reviewer",
        reviewed_at=T_REVIEW,
        assessment=DecisionReviewAssessment.SOUND,
        summary="The integrity boundary is sound.",
        findings=("Route relation reads through ExperienceService.",),
        candidate_lessons=("One service should own provenance validation.",),
        confidence=DecisionReviewConfidence.HIGH,
        idempotency_key="knowledge-integrity-review",
    )
    decision_repository.save(decision)
    acceptance_repository.save(acceptance)
    outcome_repository.save(outcome)
    review_repository.save(review)

    review_service = DecisionReviewService(
        review_repository,
        decision_repository,
        acceptance_repository,
        outcome_repository,
    )
    experience_service = ExperienceService(
        experience_repository,
        observation_repository,
        review_service,
    )
    knowledge_service = KnowledgeService(knowledge_repository, experience_service)
    return RealBoundary(
        decision_repository,
        acceptance_repository,
        outcome_repository,
        review_repository,
        experience_repository,
        observation_repository,
        knowledge_repository,
        experience_service,
        knowledge_service,
        decision,
        acceptance,
        outcome,
        review,
    )


def promote_valid_experience(boundary: RealBoundary) -> Experience:
    return boundary.experience_service.add_from_decision_review(
        decision_review_id=boundary.review.id,
        source_selectors=[
            DecisionReviewPromotionSelector(DecisionReviewPromotionSourceKind.FINDING, 0)
        ],
        promoted_by="learning-owner",
        promotion_reason="The reviewed finding is reusable.",
        idempotency_key="knowledge-integrity-promotion",
        title="Validated promoted Experience",
        context="Decision review follow-up",
        action="Promote one reviewed finding",
        outcome="Experience preserves validated provenance",
        result=ExperienceResult.SUCCESS,
    )


def corrupt_promoted_experience(
    boundary: RealBoundary,
    *,
    review_id: UUID | None = None,
    index: int = 0,
    text: str = "Route relation reads through ExperienceService.",
) -> Experience:
    experience = Experience(
        id=UUID("66666666-6666-6666-6666-666666666666"),
        timestamp=T_EXPERIENCE,
        title="Persisted promoted Experience",
        context="Integrity boundary fixture",
        action="Use reviewed learning",
        outcome="Stored provenance is inspected",
        result=ExperienceResult.SUCCESS,
        decision_review_promotion=DecisionReviewPromotion(
            decision_review_id=review_id or boundary.review.id,
            source_statements=(
                DecisionReviewPromotionSourceStatement(
                    kind=DecisionReviewPromotionSourceKind.FINDING,
                    index=index,
                    text=text,
                ),
            ),
            promoted_by="learning-owner",
            promotion_reason="Persisted fixture.",
            idempotency_key="persisted-corrupt-promotion",
        ),
    )
    boundary.experience_repository.save(experience)
    return experience


def knowledge_for(experience: Experience) -> Knowledge:
    return Knowledge(
        id=UUID("77777777-7777-7777-7777-777777777777"),
        timestamp=T_KNOWLEDGE,
        statement="Preserve one validation owner",
        rationale="The linked Experience must remain valid.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience.id],
    )


def test_valid_promoted_experience_creates_explicit_generic_knowledge(tmp_path: Path) -> None:
    boundary = make_boundary(tmp_path)
    experience = promote_valid_experience(boundary)

    knowledge = boundary.knowledge_service.add_from_experience(
        experience.id,
        "Reuse validated promoted learning",
        "The caller explicitly generalized the Experience.",
        KnowledgeConfidence.HIGH,
        ["manual"],
    )

    assert knowledge.experience_ids == [experience.id]
    assert boundary.knowledge_repository.load_all() == [knowledge]


def test_ordinary_and_observation_derived_experiences_remain_valid_evidence(
    tmp_path: Path,
) -> None:
    boundary = make_boundary(tmp_path)
    observation = Observation(
        id=UUID("88888888-8888-8888-8888-888888888888"),
        timestamp=T_CREATED,
        content="A source-backed observation.",
        source="pytest",
    )
    boundary.observation_repository.save(observation)
    ordinary = boundary.experience_service.add(
        "Ordinary Experience",
        "Direct capture",
        "Record the result",
        "Ordinary evidence remains valid",
        ExperienceResult.SUCCESS,
    )
    derived = boundary.experience_service.add_from_observation(
        observation.id,
        "Observation-derived Experience",
        "Interpret the observation",
        "Derived evidence remains valid",
        ExperienceResult.SUCCESS,
    )

    knowledge = boundary.knowledge_service.add(
        "Ordinary Experience semantics remain unchanged",
        "Both non-promoted paths pass the validated reader.",
        KnowledgeConfidence.MEDIUM,
        [ordinary.id, derived.id],
    )

    assert knowledge.experience_ids == [ordinary.id, derived.id]


def test_missing_review_ancestry_blocks_creation_without_save(tmp_path: Path) -> None:
    boundary = make_boundary(tmp_path)
    missing_review_id = UUID("99999999-9999-9999-9999-999999999999")
    experience = corrupt_promoted_experience(boundary, review_id=missing_review_id)

    with pytest.raises(DecisionReviewNotFoundError):
        boundary.knowledge_service.add_from_experience(
            experience.id,
            "Rejected knowledge",
            "Review ancestry is absent.",
            KnowledgeConfidence.LOW,
        )

    assert boundary.knowledge_repository.load_all() == []


def test_malformed_review_relation_blocks_creation_without_save(tmp_path: Path) -> None:
    boundary = make_boundary(tmp_path)
    malformed_review = boundary.review.model_copy(
        update={
            "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "decision_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        }
    )
    boundary.review_repository.save(malformed_review)
    experience = corrupt_promoted_experience(boundary, review_id=malformed_review.id)

    with pytest.raises(DecisionReviewDecisionNotFoundError):
        boundary.knowledge_service.add(
            "Rejected knowledge",
            "Review relations are malformed.",
            KnowledgeConfidence.LOW,
            [experience.id],
        )

    assert boundary.knowledge_repository.load_all() == []


@pytest.mark.parametrize(
    ("index", "text", "expected_error"),
    [
        (
            4,
            "Route relation reads through ExperienceService.",
            DecisionReviewPromotionSourceIndexError,
        ),
        (
            0,
            "Persisted text no longer matches the Review.",
            DecisionReviewPromotionSourceTextMismatchError,
        ),
    ],
)
def test_corrupt_promotion_source_blocks_creation_and_reads(
    tmp_path: Path,
    index: int,
    text: str,
    expected_error: type[Exception],
) -> None:
    boundary = make_boundary(tmp_path)
    experience = corrupt_promoted_experience(boundary, index=index, text=text)

    with pytest.raises(expected_error):
        boundary.knowledge_service.add_from_experience(
            experience.id,
            "Rejected knowledge",
            "Promotion provenance is corrupt.",
            KnowledgeConfidence.LOW,
        )
    assert boundary.knowledge_repository.load_all() == []

    stored = knowledge_for(experience)
    boundary.knowledge_repository.save(stored)
    with pytest.raises(expected_error):
        boundary.knowledge_service.get_by_id(stored.id)
    with pytest.raises(expected_error):
        boundary.knowledge_service.list_knowledge()
    with pytest.raises(expected_error):
        boundary.knowledge_service.list_for_experience(experience.id)
