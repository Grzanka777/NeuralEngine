from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from neural_engine.domain import (
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    EvidenceReference,
)
from neural_engine.domain.decision_outcome import DecisionOutcomeMetricValue
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
from neural_engine.ports.decision_repository import DecisionRepository


class DecisionOutcomeError(Exception):
    """Base error for Decision outcome service failures."""


class DecisionOutcomeDecisionNotFoundError(DecisionOutcomeError):
    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision not found: {decision_id}")


class DecisionOutcomeAcceptanceNotFoundError(DecisionOutcomeError):
    def __init__(self, acceptance_id: UUID) -> None:
        self.acceptance_id = acceptance_id
        super().__init__(f"Decision acceptance not found: {acceptance_id}")


class DecisionOutcomeAcceptanceMismatchError(DecisionOutcomeError):
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


class DecisionOutcomeActionsRequiredError(DecisionOutcomeError):
    def __init__(self) -> None:
        super().__init__("Decision outcome requires at least one action ID.")


class DecisionOutcomeDuplicateActionError(DecisionOutcomeError):
    def __init__(self, action_id: UUID) -> None:
        self.action_id = action_id
        super().__init__(f"Decision outcome contains duplicate action ID: {action_id}")


class DecisionOutcomeActionNotFoundError(DecisionOutcomeError):
    def __init__(self, action_id: UUID) -> None:
        self.action_id = action_id
        super().__init__(f"Decision action not found: {action_id}")


class DecisionOutcomeActionDecisionMismatchError(DecisionOutcomeError):
    def __init__(
        self, action_id: UUID, expected_decision_id: UUID, actual_decision_id: UUID
    ) -> None:
        self.action_id = action_id
        self.expected_decision_id = expected_decision_id
        self.actual_decision_id = actual_decision_id
        super().__init__(
            f"Decision action {action_id} belongs to Decision {actual_decision_id}, "
            f"expected {expected_decision_id}."
        )


class DecisionOutcomeActionAcceptanceMismatchError(DecisionOutcomeError):
    def __init__(
        self, action_id: UUID, expected_acceptance_id: UUID, actual_acceptance_id: UUID
    ) -> None:
        self.action_id = action_id
        self.expected_acceptance_id = expected_acceptance_id
        self.actual_acceptance_id = actual_acceptance_id
        super().__init__(
            f"Decision action {action_id} references acceptance {actual_acceptance_id}, "
            f"expected {expected_acceptance_id}."
        )


class DecisionOutcomeValidationBeforeActionError(DecisionOutcomeError):
    def __init__(self, validated_at: datetime, earliest_started_at: datetime) -> None:
        self.validated_at = validated_at
        self.earliest_started_at = earliest_started_at
        super().__init__(
            f"Decision outcome validated_at {validated_at.isoformat()} precedes earliest "
            f"linked action start {earliest_started_at.isoformat()}."
        )


class DecisionOutcomeNotFoundError(DecisionOutcomeError):
    def __init__(self, outcome_id: UUID) -> None:
        self.outcome_id = outcome_id
        super().__init__(f"Decision outcome not found: {outcome_id}")


class DecisionOutcomeIdempotencyConflictError(DecisionOutcomeError):
    def __init__(self, decision_id: UUID, idempotency_key: str) -> None:
        self.decision_id = decision_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Decision outcome idempotency key {idempotency_key!r} already exists for "
            f"Decision {decision_id} with a different payload."
        )


class DecisionOutcomeIdempotencyAmbiguityError(DecisionOutcomeError):
    def __init__(self, decision_id: UUID, idempotency_key: str, match_count: int) -> None:
        self.decision_id = decision_id
        self.idempotency_key = idempotency_key
        self.match_count = match_count
        super().__init__(
            f"Decision outcome idempotency key {idempotency_key!r} is ambiguous for "
            f"Decision {decision_id}: {match_count} persisted outcomes share the same key."
        )


class DecisionOutcomeSummary(BaseModel):
    """Immutable, non-persisted projection of outcomes for one Decision."""

    model_config = ConfigDict(frozen=True)

    decision_id: UUID
    outcome_count: int
    latest_result: DecisionOutcomeResult | None
    latest_validated_at: datetime | None
    linked_action_count: int
    results_by_type: Mapping[str, int]
    has_success: bool
    has_failure: bool

    @field_validator("results_by_type")
    @classmethod
    def _freeze_results(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        return MappingProxyType(dict(value))

    @field_serializer("results_by_type")
    def _serialize_results(self, value: Mapping[str, int]) -> dict[str, int]:
        return {key: value[key] for key in sorted(value)}


class DecisionOutcomeService:
    """Application service for factual results of recorded Decision actions."""

    def __init__(
        self,
        outcome_repository: DecisionOutcomeRepository,
        decision_repository: DecisionRepository,
        acceptance_repository: DecisionAcceptanceRepository,
        action_repository: DecisionActionRepository,
    ) -> None:
        self._outcome_repository = outcome_repository
        self._decision_repository = decision_repository
        self._acceptance_repository = acceptance_repository
        self._action_repository = action_repository

    def add(
        self,
        decision_id: UUID,
        acceptance_id: UUID,
        action_ids: list[UUID],
        result: DecisionOutcomeResult,
        summary: str,
        validated_by: str,
        validated_at: datetime,
        idempotency_key: str,
        evidence_references: list[EvidenceReference] | None = None,
        metrics: Mapping[str, DecisionOutcomeMetricValue] | None = None,
        tags: list[str] | None = None,
    ) -> DecisionOutcome:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionOutcomeDecisionNotFoundError(decision_id)

        acceptance = self._acceptance_repository.get_by_id(acceptance_id)
        if acceptance is None:
            raise DecisionOutcomeAcceptanceNotFoundError(acceptance_id)
        if acceptance.decision_id != decision_id:
            raise DecisionOutcomeAcceptanceMismatchError(
                acceptance_id, decision_id, acceptance.decision_id
            )

        if not action_ids:
            raise DecisionOutcomeActionsRequiredError()
        seen: set[UUID] = set()
        for action_id in action_ids:
            if action_id in seen:
                raise DecisionOutcomeDuplicateActionError(action_id)
            seen.add(action_id)

        actions = [
            self._load_and_validate_action(action_id, decision_id, acceptance_id)
            for action_id in action_ids
        ]
        earliest_started_at = min(action.started_at for action in actions)
        if validated_at.tzinfo is not None and validated_at < earliest_started_at:
            raise DecisionOutcomeValidationBeforeActionError(validated_at, earliest_started_at)

        candidate = DecisionOutcome(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            action_ids=tuple(action_ids),
            result=result,
            summary=summary,
            validated_by=validated_by,
            validated_at=validated_at,
            evidence_references=tuple(evidence_references or []),
            metrics=metrics or {},
            idempotency_key=idempotency_key,
            tags=tuple(tags or []),
        )

        outcomes = self._outcome_repository.load_all()
        existing = self._find_by_idempotency_key(outcomes, candidate)
        if existing is not None:
            if self._semantic_payload(existing) == self._semantic_payload(candidate):
                return existing
            raise DecisionOutcomeIdempotencyConflictError(decision_id, idempotency_key)

        self._outcome_repository.save(candidate)
        return candidate

    def list_for_decision(self, decision_id: UUID) -> list[DecisionOutcome]:
        self._require_decision(decision_id)
        return [
            outcome
            for outcome in self._outcome_repository.load_all()
            if outcome.decision_id == decision_id
        ]

    def show(self, outcome_id: UUID) -> DecisionOutcome:
        outcome = self._outcome_repository.get_by_id(outcome_id)
        if outcome is None:
            raise DecisionOutcomeNotFoundError(outcome_id)
        return outcome

    def summary_for_decision(self, decision_id: UUID) -> DecisionOutcomeSummary:
        self._require_decision(decision_id)
        outcomes = [
            outcome
            for outcome in self._outcome_repository.load_all()
            if outcome.decision_id == decision_id
        ]
        for outcome in outcomes:
            self._validate_outcome_relations(outcome)

        latest = max(outcomes, key=lambda item: (item.validated_at, str(item.id)), default=None)
        result_counts = {result.value: 0 for result in DecisionOutcomeResult}
        linked_action_ids: set[UUID] = set()
        for outcome in outcomes:
            result_counts[outcome.result.value] += 1
            linked_action_ids.update(outcome.action_ids)

        return DecisionOutcomeSummary(
            decision_id=decision_id,
            outcome_count=len(outcomes),
            latest_result=latest.result if latest is not None else None,
            latest_validated_at=latest.validated_at if latest is not None else None,
            linked_action_count=len(linked_action_ids),
            results_by_type=result_counts,
            has_success=result_counts[DecisionOutcomeResult.SUCCEEDED.value] > 0,
            has_failure=result_counts[DecisionOutcomeResult.FAILED.value] > 0,
        )

    def _require_decision(self, decision_id: UUID) -> None:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionOutcomeDecisionNotFoundError(decision_id)

    def _load_and_validate_action(
        self, action_id: UUID, decision_id: UUID, acceptance_id: UUID
    ) -> DecisionAction:
        action = self._action_repository.get_by_id(action_id)
        if action is None:
            raise DecisionOutcomeActionNotFoundError(action_id)
        if action.decision_id != decision_id:
            raise DecisionOutcomeActionDecisionMismatchError(
                action_id, decision_id, action.decision_id
            )
        if action.acceptance_id != acceptance_id:
            raise DecisionOutcomeActionAcceptanceMismatchError(
                action_id, acceptance_id, action.acceptance_id
            )
        return action

    def _validate_outcome_relations(self, outcome: DecisionOutcome) -> None:
        acceptance = self._acceptance_repository.get_by_id(outcome.acceptance_id)
        if acceptance is None:
            raise DecisionOutcomeAcceptanceNotFoundError(outcome.acceptance_id)
        if acceptance.decision_id != outcome.decision_id:
            raise DecisionOutcomeAcceptanceMismatchError(
                outcome.acceptance_id, outcome.decision_id, acceptance.decision_id
            )
        actions = [
            self._load_and_validate_action(action_id, outcome.decision_id, outcome.acceptance_id)
            for action_id in outcome.action_ids
        ]
        earliest_started_at = min(action.started_at for action in actions)
        if outcome.validated_at < earliest_started_at:
            raise DecisionOutcomeValidationBeforeActionError(
                outcome.validated_at, earliest_started_at
            )

    @staticmethod
    def _find_by_idempotency_key(
        outcomes: list[DecisionOutcome], candidate: DecisionOutcome
    ) -> DecisionOutcome | None:
        matches = [
            outcome
            for outcome in outcomes
            if outcome.decision_id == candidate.decision_id
            and outcome.idempotency_key == candidate.idempotency_key
        ]
        if len(matches) > 1:
            raise DecisionOutcomeIdempotencyAmbiguityError(
                candidate.decision_id, candidate.idempotency_key, len(matches)
            )
        return matches[0] if matches else None

    @staticmethod
    def _semantic_payload(outcome: DecisionOutcome) -> dict[str, object]:
        payload = outcome.model_dump(mode="json", exclude={"id", "recorded_at"})
        payload["evidence_references"] = [
            evidence.model_dump(mode="json", exclude={"captured_at"})
            for evidence in outcome.evidence_references
        ]
        return payload
