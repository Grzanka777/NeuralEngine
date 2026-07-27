from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from neural_engine.application.decision_acceptance_service import DecisionAcceptanceService
from neural_engine.application.decision_action_service import DecisionActionService
from neural_engine.application.decision_outcome_service import DecisionOutcomeService
from neural_engine.application.decision_review_service import DecisionReviewService
from neural_engine.application.decision_service import DecisionService
from neural_engine.application.development_evidence_service import (
    DevelopmentEvidenceConflictError,
    DevelopmentEvidenceMismatchError,
    DevelopmentEvidenceRecordInput,
    DevelopmentEvidenceRequest,
    DevelopmentEvidenceService,
    DevelopmentEvidenceUnauthorizedError,
    ValidationTreeStrength,
)
from neural_engine.application.experience_service import ExperienceService
from neural_engine.domain import (
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
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository
from neural_engine.infrastructure.json_playbook_run_repository import JsonPlaybookRunRepository
from neural_engine.ports.development_evidence_source import (
    DevelopmentEvidenceSnapshot,
    ValidationClaim,
)


class StaticSource:
    def __init__(self, snapshot: DevelopmentEvidenceSnapshot) -> None:
        self.snapshot = snapshot
        self.read_count = 0

    def read(
        self,
        *,
        repository_root: str,
        prompt_path: str,
        review_path: str,
        commit_sha: str,
    ) -> DevelopmentEvidenceSnapshot:
        self.read_count += 1
        return self.snapshot


def _snapshot(
    *,
    claims: tuple[ValidationClaim, ...] = (ValidationClaim("uv run pytest", 0, 10),),
    attested_tree: str | None = None,
) -> DevelopmentEvidenceSnapshot:
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
        validation_claims=claims,
        validation_tree_attested=attested_tree,
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
            "result": "success",
        }
    return DevelopmentEvidenceRecordInput.model_validate(payload)


def _request() -> DevelopmentEvidenceRequest:
    return DevelopmentEvidenceRequest(
        repository_root="/tmp/NeuralEngine",
        prompt_path=".agent-work/prompts/task.md",
        review_path=".agent-work/reviews/review.md",
        commit_sha="2" * 40,
    )


def _service(
    tmp_path: Path, snapshot: DevelopmentEvidenceSnapshot | None = None
) -> tuple[DevelopmentEvidenceService, StaticSource]:
    source = StaticSource(snapshot or _snapshot())
    decision_repository = JsonDecisionRepository(tmp_path / "decisions")
    observation_repository = JsonObservationRepository(tmp_path / "observations")
    acceptance_repository = JsonDecisionAcceptanceRepository(tmp_path / "acceptances")
    action_repository = JsonDecisionActionRepository(tmp_path / "actions")
    outcome_repository = JsonDecisionOutcomeRepository(tmp_path / "outcomes")
    review_repository = JsonDecisionReviewRepository(tmp_path / "reviews")
    review_service = DecisionReviewService(
        review_repository,
        decision_repository,
        acceptance_repository,
        outcome_repository,
    )
    service = DevelopmentEvidenceService(
        source,
        DecisionService(decision_repository, observation_repository),
        DecisionAcceptanceService(acceptance_repository, decision_repository),
        DecisionActionService(
            action_repository,
            decision_repository,
            acceptance_repository,
            JsonPlaybookRunRepository(tmp_path / "runs"),
        ),
        DecisionOutcomeService(
            outcome_repository,
            decision_repository,
            acceptance_repository,
            action_repository,
        ),
        review_service,
        ExperienceService(
            JsonExperienceRepository(tmp_path / "experiences"),
            observation_repository,
            review_service,
        ),
    )
    return service, source


def test_preview_is_side_effect_free_and_separates_candidate_meaning(tmp_path: Path) -> None:
    service, source = _service(tmp_path)

    candidate = service.preview(_request(), _records())

    assert source.read_count == 1
    assert not list(tmp_path.iterdir())
    assert candidate.records.outcome_result is DecisionOutcomeResult.UNKNOWN
    assert "completed" in candidate.uncertainty[-1]
    assert candidate.proposed_writes == (
        "Decision",
        "DecisionAcceptance",
        "DecisionAction",
        "DecisionOutcome",
        "DecisionReview",
    )
    assert "Observation" in candidate.explicitly_not_created
    assert "Knowledge" in candidate.explicitly_not_created


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("prompt_review", "starting checkpoint"),
        ("review_parent", "commit parent"),
        ("paths", "changed-file inventory"),
        ("duplicate_paths", "duplicate paths"),
        ("patch", "full diff"),
    ],
)
def test_correlation_mismatch_is_rejected(tmp_path: Path, kind: str, message: str) -> None:
    snapshot = _snapshot()
    if kind == "prompt_review":
        snapshot = replace(snapshot, review_starting_checkpoint="4" * 40)
    elif kind == "review_parent":
        snapshot = replace(snapshot, commit_parent_sha="4" * 40)
    elif kind == "paths":
        snapshot = replace(snapshot, review_changed_paths=("different.py",))
    elif kind == "duplicate_paths":
        snapshot = replace(snapshot, review_changed_paths=("src/change.py", "src/change.py"))
    else:
        snapshot = replace(snapshot, patch_matches=False)
    service, _ = _service(tmp_path, snapshot)

    with pytest.raises(DevelopmentEvidenceMismatchError, match=message):
        service.preview(_request(), _records())


@pytest.mark.parametrize(
    ("claims", "attested", "expected"),
    [
        (
            (ValidationClaim("uv run pytest", 0, 10),),
            "3" * 40,
            ValidationTreeStrength.EXACT_COMMITTED_TREE_ATTESTED,
        ),
        (
            (ValidationClaim("uv run pytest", 0, 10),),
            None,
            ValidationTreeStrength.PRE_COMMIT_DIFF_MATCH,
        ),
        (
            (ValidationClaim("uv run pytest", None, 10),),
            None,
            ValidationTreeStrength.REVIEW_CLAIM_ONLY,
        ),
        ((), None, ValidationTreeStrength.ABSENT),
        (
            (ValidationClaim("uv run pytest", 1, 0),),
            None,
            ValidationTreeStrength.CONTRADICTORY,
        ),
    ],
)
def test_validation_tree_strength_is_explicit(
    tmp_path: Path,
    claims: tuple[ValidationClaim, ...],
    attested: str | None,
    expected: ValidationTreeStrength,
) -> None:
    service, _ = _service(tmp_path, _snapshot(claims=claims, attested_tree=attested))

    candidate = service.preview(_request(), _records())

    assert candidate.validation_tree_strength is expected


def test_failed_validation_does_not_infer_succeeded_outcome(tmp_path: Path) -> None:
    snapshot = _snapshot(claims=(ValidationClaim("uv run pytest", 1, 0),))
    service, _ = _service(tmp_path, snapshot)

    candidate = service.preview(_request(), _records())

    assert candidate.source_facts.review_outcome == "completed"
    assert candidate.validation_tree_strength is ValidationTreeStrength.CONTRADICTORY
    assert candidate.records.outcome_result is DecisionOutcomeResult.UNKNOWN


def test_actor_fields_are_required_and_never_inferred() -> None:
    payload = _records().model_dump()
    del payload["proposed_by"]

    with pytest.raises(ValidationError, match="proposed_by"):
        DevelopmentEvidenceRecordInput.model_validate(payload)


def test_apply_requires_explicit_authority_and_writes_nothing(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    candidate = service.preview(_request(), _records())

    with pytest.raises(DevelopmentEvidenceUnauthorizedError, match="Explicit"):
        service.apply(candidate, authority_confirmed=False)

    assert not list(tmp_path.iterdir())


def test_apply_rereads_source_and_rejects_stale_candidate(tmp_path: Path) -> None:
    service, source = _service(tmp_path)
    candidate = service.preview(_request(), _records())
    source.snapshot = replace(source.snapshot, prompt_sha256="sha256:" + "d" * 64)

    with pytest.raises(DevelopmentEvidenceConflictError, match="changed after preview"):
        service.apply(candidate, authority_confirmed=True)

    assert source.read_count == 2
    assert not list(tmp_path.iterdir())


def test_apply_writes_existing_records_in_dependency_order_and_replays(tmp_path: Path) -> None:
    service, source = _service(tmp_path)
    first_candidate = service.preview(_request(), _records())
    first = service.apply(first_candidate, authority_confirmed=True)
    second_candidate = service.preview(_request(), _records())
    second = service.apply(second_candidate, authority_confirmed=True)

    assert source.read_count == 4
    assert first.decision.id == second.decision.id
    assert first.acceptance.decision_id == first.decision.id
    assert first.action.acceptance_id == first.acceptance.id
    assert first.outcome.action_ids == (first.action.id,)
    assert first.review.outcome_ids == (first.outcome.id,)
    assert len(list((tmp_path / "decisions").glob("*.json"))) == 1
    assert len(list((tmp_path / "reviews").glob("*.json"))) == 1
    assert not (tmp_path / "observations").exists()


def test_changed_review_for_same_commit_is_visible_conflict(tmp_path: Path) -> None:
    service, source = _service(tmp_path)
    first = service.preview(_request(), _records())
    service.apply(first, authority_confirmed=True)
    source.snapshot = replace(source.snapshot, review_sha256="sha256:" + "e" * 64)
    changed = service.preview(_request(), _records())

    with pytest.raises(DevelopmentEvidenceConflictError, match="different payload"):
        service.apply(changed, authority_confirmed=True)


def test_amended_commit_has_new_replay_identity(tmp_path: Path) -> None:
    service, source = _service(tmp_path)
    first = service.preview(_request(), _records())
    amended_sha = "9" * 40
    source.snapshot = replace(source.snapshot, commit_sha=amended_sha)
    amended_request = _request().model_copy(update={"commit_sha": amended_sha})
    amended = service.preview(amended_request, _records())

    assert first.replay_identity != amended.replay_identity


def test_partial_apply_resumes_through_existing_decision_idempotency(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    candidate = service.preview(_request(), _records())
    key = service._replay_key(candidate.replay_identity)
    records = candidate.records
    preexisting = service._decision_service.add(
        project_key=records.project_key,
        title=records.title,
        objective=records.objective,
        context_summary=records.context_summary,
        alternatives=list(records.alternatives),
        proposed_option=records.proposed_option,
        rationale=records.rationale,
        proposed_by=records.proposed_by,
        idempotency_key=key,
        evidence_references=list(candidate.evidence_references),
    )

    result = service.apply(candidate, authority_confirmed=True)

    assert result.decision.id == preexisting.id
    assert result.review.decision_id == preexisting.id


def test_optional_promotion_copies_exact_selected_review_statement(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    candidate = service.preview(_request(), _records(promotion=True))

    result = service.apply(candidate, authority_confirmed=True)

    assert result.experience is not None
    promotion = result.experience.decision_review_promotion
    assert promotion is not None
    assert promotion.promoted_by == "promoter"
    assert promotion.promotion_reason == "Explicitly selected for reuse."
    assert promotion.source_statements[0].text == result.review.findings[0]


def test_references_are_bounded_and_do_not_contain_source_bodies(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    candidate = service.preview(_request(), _records())

    references = {reference.kind: reference for reference in candidate.evidence_references}
    assert references["agent_prompt"].locator == candidate.source_facts.prompt_path
    assert references["agent_review"].content_hash == candidate.source_facts.review_sha256
    assert references["git_commit"].locator == candidate.source_facts.commit_sha
    assert references["validation_run"].content_hash == candidate.source_facts.review_sha256
    assert all("diff --git" not in (reference.summary or "") for reference in references.values())
