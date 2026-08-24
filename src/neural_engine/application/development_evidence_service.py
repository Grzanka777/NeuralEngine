from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from neural_engine.application.brain_trust_transition import BrainTrustMutationError
from neural_engine.application.decision_acceptance_service import (
    DecisionAcceptanceIdempotencyConflictError,
    DecisionAcceptanceService,
)
from neural_engine.application.decision_action_service import (
    DecisionActionIdempotencyConflictError,
    DecisionActionService,
)
from neural_engine.application.decision_outcome_service import (
    DecisionOutcomeIdempotencyConflictError,
    DecisionOutcomeService,
)
from neural_engine.application.decision_review_service import (
    DecisionReviewIdempotencyConflictError,
    DecisionReviewService,
)
from neural_engine.application.decision_service import (
    DecisionIdempotencyConflictError,
    DecisionService,
)
from neural_engine.application.experience_service import (
    DecisionReviewPromotionIdempotencyConflictError,
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
    EvidenceReference,
    Experience,
    ExperienceResult,
)
from neural_engine.domain.decision_outcome import DecisionOutcomeMetricValue
from neural_engine.ports.development_evidence_source import (
    DevelopmentEvidenceSnapshot,
    DevelopmentEvidenceSource,
)

_REPLAY_NAMESPACE = UUID("8a590540-cf2b-49aa-b0d7-4fda0becf495")


class DevelopmentEvidenceError(Exception):
    """Base application orchestration error."""


class DevelopmentEvidenceMismatchError(DevelopmentEvidenceError):
    """Prompt, review, and Git evidence do not describe the same bundle."""


class DevelopmentEvidenceInsufficientError(DevelopmentEvidenceError):
    """The evidence is present but not strong enough for the supported topology."""


class DevelopmentEvidenceUnauthorizedError(DevelopmentEvidenceError):
    """Apply was attempted without explicit caller authority."""


class DevelopmentEvidenceConflictError(DevelopmentEvidenceError):
    """A stale candidate or conflicting durable replay was detected."""


class DevelopmentEvidenceTrustError(DevelopmentEvidenceError):
    """A component publication was rejected or failed under Brain Trust."""


class ValidationTreeStrength(StrEnum):
    EXACT_COMMITTED_TREE_ATTESTED = "exact committed tree attested"
    PRE_COMMIT_DIFF_MATCH = "review diff matches commit but validation was pre-commit"
    REVIEW_CLAIM_ONLY = "review claim only"
    ABSENT = "absent"
    CONTRADICTORY = "contradictory"


class PromotionSelectorInput(BaseModel):
    """Explicit statement position selected by the applying caller."""

    model_config = ConfigDict(frozen=True)

    kind: DecisionReviewPromotionSourceKind
    index: int

    @field_validator("index")
    @classmethod
    def _index_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Promotion selector index must not be negative.")
        return value


class ExperiencePromotionInput(BaseModel):
    """All explicit semantics for optional Review-to-Experience promotion."""

    model_config = ConfigDict(frozen=True)

    source_selectors: tuple[PromotionSelectorInput, ...]
    promoted_by: str
    promotion_reason: str
    title: str
    context: str
    action: str
    outcome: str
    result: ExperienceResult
    observation_ids: tuple[UUID, ...] = ()
    tags: tuple[str, ...] = ()

    @field_validator("source_selectors")
    @classmethod
    def _selectors_must_be_present(
        cls, value: tuple[PromotionSelectorInput, ...]
    ) -> tuple[PromotionSelectorInput, ...]:
        if not value:
            raise ValueError("Experience promotion requires at least one source selector.")
        return value


class DevelopmentEvidenceRecordInput(BaseModel):
    """Caller-owned semantic content and attribution for selected existing records."""

    model_config = ConfigDict(frozen=True)

    project_key: str
    title: str
    objective: str
    context_summary: str
    alternatives: tuple[str, ...]
    proposed_option: str
    rationale: str
    proposed_by: str
    observation_ids: tuple[UUID, ...] = ()
    accepted_by: str
    acceptance_reason: str
    action_type: str
    action_summary: str
    performed_by: str
    started_at: datetime
    completed_at: datetime | None = None
    outcome_result: DecisionOutcomeResult
    outcome_summary: str
    validated_by: str
    validated_at: datetime
    outcome_metrics: dict[str, DecisionOutcomeMetricValue] = Field(default_factory=dict)
    reviewed_by: str
    reviewed_at: datetime
    review_assessment: DecisionReviewAssessment
    review_summary: str
    findings: tuple[str, ...]
    candidate_lessons: tuple[str, ...] = ()
    review_confidence: DecisionReviewConfidence
    tags: tuple[str, ...] = ()
    promotion: ExperiencePromotionInput | None = None

    @field_validator("started_at", "completed_at", "validated_at", "reviewed_at")
    @classmethod
    def _timestamps_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Development evidence semantic timestamps must be timezone-aware.")
        return value.astimezone(UTC) if value is not None else None


class DevelopmentEvidenceRequest(BaseModel):
    """One explicitly selected local source bundle."""

    model_config = ConfigDict(frozen=True)

    repository_root: str
    prompt_path: str
    review_path: str
    commit_sha: str


class DevelopmentEvidenceCandidate(BaseModel):
    """A replaceable application preview; never a persisted authority record."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    request: DevelopmentEvidenceRequest
    records: DevelopmentEvidenceRecordInput
    source_facts: DevelopmentEvidenceSnapshot
    validation_tree_strength: ValidationTreeStrength
    interpretation: tuple[str, ...]
    uncertainty: tuple[str, ...]
    evidence_references: tuple[EvidenceReference, ...]
    proposed_writes: tuple[str, ...]
    explicitly_not_created: tuple[str, ...]
    replay_identity: str
    partial_apply_semantics: str


class DevelopmentEvidenceApplyResult(BaseModel):
    """Records created or replayed in dependency order."""

    model_config = ConfigDict(frozen=True)

    decision: Decision
    acceptance: DecisionAcceptance
    action: DecisionAction
    outcome: DecisionOutcome
    review: DecisionReview
    experience: Experience | None = None


class DevelopmentEvidenceService:
    """Preview and explicitly apply one correlated local development bundle."""

    def __init__(
        self,
        source: DevelopmentEvidenceSource,
        decision_service: DecisionService,
        acceptance_service: DecisionAcceptanceService,
        action_service: DecisionActionService,
        outcome_service: DecisionOutcomeService,
        review_service: DecisionReviewService,
        experience_service: ExperienceService,
    ) -> None:
        self._source = source
        self._decision_service = decision_service
        self._acceptance_service = acceptance_service
        self._action_service = action_service
        self._outcome_service = outcome_service
        self._review_service = review_service
        self._experience_service = experience_service

    def preview(
        self,
        request: DevelopmentEvidenceRequest,
        records: DevelopmentEvidenceRecordInput,
    ) -> DevelopmentEvidenceCandidate:
        snapshot = self._read(request)
        self._correlate(snapshot)
        strength = self._classify_validation(snapshot)
        references = self._references(snapshot)
        replay_identity = f"{snapshot.repository_identity}:{snapshot.commit_sha}"
        replay_key = self._replay_key(replay_identity)
        self._validate_domain_payload(records, references, replay_key)

        uncertainty = [
            "Review prose is a claim, not durable factual authority.",
            "Correlation does not prove causality or authenticate any actor.",
        ]
        if strength is not ValidationTreeStrength.EXACT_COMMITTED_TREE_ATTESTED:
            uncertainty.append(
                "Validation evidence does not attest execution on the exact committed tree."
            )
        if snapshot.review_outcome == "completed":
            uncertainty.append(
                "The review outcome 'completed' does not determine DecisionOutcome.result."
            )

        proposed_writes = [
            "Decision",
            "DecisionAcceptance",
            "DecisionAction",
            "DecisionOutcome",
            "DecisionReview",
        ]
        if records.promotion is not None:
            proposed_writes.append("Experience")

        return DevelopmentEvidenceCandidate(
            request=request,
            records=records,
            source_facts=snapshot,
            validation_tree_strength=strength,
            interpretation=(
                "The caller proposes the supplied Decision-family semantics for this bundle.",
            ),
            uncertainty=tuple(uncertainty),
            evidence_references=references,
            proposed_writes=tuple(proposed_writes),
            explicitly_not_created=(
                "Observation",
                "Knowledge",
                "Playbook",
                "PlaybookRevision",
                "PlaybookRun",
                "PlaybookEvaluation",
                "EvolutionProposal",
                "PlaybookRevisionActivation",
                "PlaybookRevisionApplication",
            ),
            replay_identity=replay_identity,
            partial_apply_semantics=(
                "Each record is one independently controlled generation; writes are not "
                "transactional. An exact rerun resumes through record-service idempotency, "
                "while a pending Brain Trust transition remains fail-closed for explicit "
                "recovery."
            ),
        )

    def apply(
        self,
        candidate: DevelopmentEvidenceCandidate,
        *,
        authority_confirmed: bool,
    ) -> DevelopmentEvidenceApplyResult:
        if not authority_confirmed:
            raise DevelopmentEvidenceUnauthorizedError(
                "Explicit apply authority is required; preview never writes."
            )

        fresh = self.preview(candidate.request, candidate.records)
        if fresh.source_facts != candidate.source_facts:
            raise DevelopmentEvidenceConflictError(
                "Prompt, review, or Git evidence changed after preview; apply is rejected."
            )

        records = fresh.records
        references = list(fresh.evidence_references)
        key = self._replay_key(fresh.replay_identity)
        try:
            decision = self._decision_service.add(
                project_key=records.project_key,
                title=records.title,
                objective=records.objective,
                context_summary=records.context_summary,
                alternatives=list(records.alternatives),
                proposed_option=records.proposed_option,
                rationale=records.rationale,
                proposed_by=records.proposed_by,
                idempotency_key=key,
                observation_ids=list(records.observation_ids),
                evidence_references=references,
                tags=list(records.tags),
            )
            acceptance = self._acceptance_service.accept(
                decision_id=decision.id,
                accepted_by=records.accepted_by,
                reason=records.acceptance_reason,
                idempotency_key=key,
                evidence_references=references,
                tags=list(records.tags),
            )
            action = self._action_service.add(
                decision_id=decision.id,
                acceptance_id=acceptance.id,
                action_type=records.action_type,
                summary=records.action_summary,
                performed_by=records.performed_by,
                started_at=records.started_at,
                completed_at=records.completed_at,
                idempotency_key=key,
                evidence_references=references,
                tags=list(records.tags),
            )
            outcome = self._outcome_service.add(
                decision_id=decision.id,
                acceptance_id=acceptance.id,
                action_ids=[action.id],
                result=records.outcome_result,
                summary=records.outcome_summary,
                validated_by=records.validated_by,
                validated_at=records.validated_at,
                metrics=records.outcome_metrics,
                idempotency_key=key,
                evidence_references=references,
                tags=list(records.tags),
            )
            review = self._review_service.add(
                decision_id=decision.id,
                acceptance_id=acceptance.id,
                outcome_ids=[outcome.id],
                reviewed_by=records.reviewed_by,
                reviewed_at=records.reviewed_at,
                assessment=records.review_assessment,
                summary=records.review_summary,
                findings=list(records.findings),
                candidate_lessons=list(records.candidate_lessons),
                confidence=records.review_confidence,
                idempotency_key=key,
                evidence_references=references,
                tags=list(records.tags),
            )
            experience = self._promote(records.promotion, review, key)
        except BrainTrustMutationError as error:
            raise DevelopmentEvidenceTrustError(str(error)) from error
        except (
            DecisionIdempotencyConflictError,
            DecisionAcceptanceIdempotencyConflictError,
            DecisionActionIdempotencyConflictError,
            DecisionOutcomeIdempotencyConflictError,
            DecisionReviewIdempotencyConflictError,
            DecisionReviewPromotionIdempotencyConflictError,
        ) as error:
            raise DevelopmentEvidenceConflictError(str(error)) from error

        return DevelopmentEvidenceApplyResult(
            decision=decision,
            acceptance=acceptance,
            action=action,
            outcome=outcome,
            review=review,
            experience=experience,
        )

    def _read(self, request: DevelopmentEvidenceRequest) -> DevelopmentEvidenceSnapshot:
        return self._source.read(
            repository_root=request.repository_root,
            prompt_path=request.prompt_path,
            review_path=request.review_path,
            commit_sha=request.commit_sha,
        )

    @staticmethod
    def _correlate(snapshot: DevelopmentEvidenceSnapshot) -> None:
        if snapshot.prompt_starting_checkpoint != snapshot.review_starting_checkpoint:
            raise DevelopmentEvidenceMismatchError(
                "Prompt and review starting checkpoints do not match."
            )
        if snapshot.review_starting_checkpoint != snapshot.commit_parent_sha:
            raise DevelopmentEvidenceMismatchError(
                "Review starting checkpoint does not match commit parent."
            )
        if set(snapshot.review_changed_paths) != set(snapshot.commit_changed_paths):
            raise DevelopmentEvidenceMismatchError(
                "Review changed-file inventory does not match commit changed paths."
            )
        if len(snapshot.review_changed_paths) != len(set(snapshot.review_changed_paths)):
            raise DevelopmentEvidenceMismatchError(
                "Review changed-file inventory contains duplicate paths."
            )
        if not snapshot.patch_matches:
            raise DevelopmentEvidenceMismatchError(
                "Review full diff does not match the local commit patch."
            )

    @staticmethod
    def _classify_validation(
        snapshot: DevelopmentEvidenceSnapshot,
    ) -> ValidationTreeStrength:
        claims = snapshot.validation_claims
        if any(claim.exit_code is not None and claim.exit_code != 0 for claim in claims):
            return ValidationTreeStrength.CONTRADICTORY
        if not claims:
            return ValidationTreeStrength.ABSENT
        if snapshot.validation_tree_attested == snapshot.commit_tree_sha and all(
            claim.exit_code == 0 for claim in claims
        ):
            return ValidationTreeStrength.EXACT_COMMITTED_TREE_ATTESTED
        if snapshot.patch_matches and all(claim.exit_code == 0 for claim in claims):
            return ValidationTreeStrength.PRE_COMMIT_DIFF_MATCH
        return ValidationTreeStrength.REVIEW_CLAIM_ONLY

    @staticmethod
    def _references(
        snapshot: DevelopmentEvidenceSnapshot,
    ) -> tuple[EvidenceReference, ...]:
        captured_at = datetime.now(UTC)
        return (
            EvidenceReference(
                kind="agent_prompt",
                locator=snapshot.prompt_path,
                repository_or_project=snapshot.repository_identity,
                content_hash=snapshot.prompt_sha256,
                captured_at=captured_at,
                source="local_development_evidence",
                summary="Explicit repository-local implementation prompt.",
            ),
            EvidenceReference(
                kind="agent_review",
                locator=snapshot.review_path,
                repository_or_project=snapshot.repository_identity,
                content_hash=snapshot.review_sha256,
                captured_at=captured_at,
                source="local_development_evidence",
                summary="Explicit repository-local implementation review.",
            ),
            EvidenceReference(
                kind="git_commit",
                locator=snapshot.commit_sha,
                repository_or_project=snapshot.repository_identity,
                content_hash=f"git-tree:{snapshot.commit_tree_sha}",
                captured_at=captured_at,
                source="local_development_evidence",
                summary=snapshot.commit_subject[:1000],
            ),
            EvidenceReference(
                kind="validation_run",
                locator=f"{snapshot.review_path}#validation",
                repository_or_project=snapshot.repository_identity,
                content_hash=snapshot.review_sha256,
                captured_at=captured_at,
                source="local_development_evidence",
                summary=f"{len(snapshot.validation_claims)} validation command claim(s) in review.",
            ),
        )

    @staticmethod
    def _replay_key(replay_identity: str) -> str:
        return f"development-evidence:{uuid5(_REPLAY_NAMESPACE, replay_identity)}"

    @staticmethod
    def _validate_domain_payload(
        records: DevelopmentEvidenceRecordInput,
        references: tuple[EvidenceReference, ...],
        key: str,
    ) -> None:
        decision_id = uuid5(_REPLAY_NAMESPACE, f"{key}:decision")
        acceptance_id = uuid5(_REPLAY_NAMESPACE, f"{key}:acceptance")
        action_id = uuid5(_REPLAY_NAMESPACE, f"{key}:action")
        outcome_id = uuid5(_REPLAY_NAMESPACE, f"{key}:outcome")
        Decision(
            id=decision_id,
            project_key=records.project_key,
            title=records.title,
            objective=records.objective,
            context_summary=records.context_summary,
            alternatives=records.alternatives,
            proposed_option=records.proposed_option,
            rationale=records.rationale,
            observation_ids=records.observation_ids,
            evidence_references=references,
            proposed_by=records.proposed_by,
            idempotency_key=key,
            tags=records.tags,
        )
        DecisionAcceptance(
            id=acceptance_id,
            decision_id=decision_id,
            accepted_by=records.accepted_by,
            reason=records.acceptance_reason,
            evidence_references=references,
            idempotency_key=key,
            tags=records.tags,
        )
        DecisionAction(
            id=action_id,
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            action_type=records.action_type,
            summary=records.action_summary,
            performed_by=records.performed_by,
            started_at=records.started_at,
            completed_at=records.completed_at,
            evidence_references=references,
            idempotency_key=key,
            tags=records.tags,
        )
        DecisionOutcome(
            id=outcome_id,
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            action_ids=(action_id,),
            result=records.outcome_result,
            summary=records.outcome_summary,
            validated_by=records.validated_by,
            validated_at=records.validated_at,
            evidence_references=references,
            metrics=records.outcome_metrics,
            idempotency_key=key,
            tags=records.tags,
        )
        DecisionReview(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            outcome_ids=(outcome_id,),
            reviewed_by=records.reviewed_by,
            reviewed_at=records.reviewed_at,
            assessment=records.review_assessment,
            summary=records.review_summary,
            findings=records.findings,
            candidate_lessons=records.candidate_lessons,
            evidence_references=references,
            confidence=records.review_confidence,
            idempotency_key=key,
            tags=records.tags,
        )
        if records.promotion is not None:
            Experience(
                title=records.promotion.title,
                context=records.promotion.context,
                action=records.promotion.action,
                outcome=records.promotion.outcome,
                result=records.promotion.result,
                observation_ids=list(records.promotion.observation_ids),
                tags=list(records.promotion.tags),
            )

    def _promote(
        self,
        promotion: ExperiencePromotionInput | None,
        review: DecisionReview,
        key: str,
    ) -> Experience | None:
        if promotion is None:
            return None
        return self._experience_service.add_from_decision_review(
            decision_review_id=review.id,
            source_selectors=[
                DecisionReviewPromotionSelector(kind=item.kind, index=item.index)
                for item in promotion.source_selectors
            ],
            promoted_by=promotion.promoted_by,
            promotion_reason=promotion.promotion_reason,
            idempotency_key=key,
            title=promotion.title,
            context=promotion.context,
            action=promotion.action,
            outcome=promotion.outcome,
            result=promotion.result,
            observation_ids=list(promotion.observation_ids),
            tags=list(promotion.tags),
        )
