from datetime import datetime
from enum import StrEnum
from uuid import UUID

from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
from neural_engine.ports.decision_repository import DecisionRepository


class DecisionLifecycleState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    OUTCOME_UNKNOWN = "outcome_unknown"


class DecisionLifecycleError(Exception):
    """Base error for Decision lifecycle projection failures."""


class DecisionLifecycleDecisionNotFoundError(DecisionLifecycleError):
    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision not found: {decision_id}")


class DecisionLifecycleMultipleAcceptancesError(DecisionLifecycleError):
    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision has multiple acceptance records: {decision_id}")


class DecisionLifecycleActionAcceptanceMismatchError(DecisionLifecycleError):
    def __init__(
        self,
        action_id: UUID,
        expected_acceptance_id: UUID | None,
        actual_acceptance_id: UUID,
    ) -> None:
        self.action_id = action_id
        self.expected_acceptance_id = expected_acceptance_id
        self.actual_acceptance_id = actual_acceptance_id
        expected = str(expected_acceptance_id) if expected_acceptance_id is not None else "none"
        super().__init__(
            f"Decision action {action_id} references acceptance {actual_acceptance_id}, "
            f"expected {expected}."
        )


class DecisionLifecycleOutcomeAcceptanceMismatchError(DecisionLifecycleError):
    def __init__(
        self,
        outcome_id: UUID,
        expected_acceptance_id: UUID | None,
        actual_acceptance_id: UUID,
    ) -> None:
        self.outcome_id = outcome_id
        self.expected_acceptance_id = expected_acceptance_id
        self.actual_acceptance_id = actual_acceptance_id
        expected = str(expected_acceptance_id) if expected_acceptance_id is not None else "none"
        super().__init__(
            f"Decision outcome {outcome_id} references acceptance {actual_acceptance_id}, "
            f"expected {expected}."
        )


class DecisionLifecycleOutcomeActionNotFoundError(DecisionLifecycleError):
    def __init__(self, outcome_id: UUID, action_id: UUID) -> None:
        self.outcome_id = outcome_id
        self.action_id = action_id
        super().__init__(f"Decision outcome {outcome_id} references missing action {action_id}.")


class DecisionLifecycleOutcomeActionDecisionMismatchError(DecisionLifecycleError):
    def __init__(
        self,
        outcome_id: UUID,
        action_id: UUID,
        expected_decision_id: UUID,
        actual_decision_id: UUID,
    ) -> None:
        self.outcome_id = outcome_id
        self.action_id = action_id
        self.expected_decision_id = expected_decision_id
        self.actual_decision_id = actual_decision_id
        super().__init__(
            f"Decision outcome {outcome_id} references action {action_id} for Decision "
            f"{actual_decision_id}, expected {expected_decision_id}."
        )


class DecisionLifecycleOutcomeActionAcceptanceMismatchError(DecisionLifecycleError):
    def __init__(
        self,
        outcome_id: UUID,
        action_id: UUID,
        expected_acceptance_id: UUID,
        actual_acceptance_id: UUID,
    ) -> None:
        self.outcome_id = outcome_id
        self.action_id = action_id
        self.expected_acceptance_id = expected_acceptance_id
        self.actual_acceptance_id = actual_acceptance_id
        super().__init__(
            f"Decision outcome {outcome_id} references action {action_id} with acceptance "
            f"{actual_acceptance_id}, expected {expected_acceptance_id}."
        )


class DecisionLifecycleOutcomeValidationBeforeActionError(DecisionLifecycleError):
    def __init__(
        self, outcome_id: UUID, validated_at: datetime, earliest_started_at: datetime
    ) -> None:
        self.outcome_id = outcome_id
        self.validated_at = validated_at
        self.earliest_started_at = earliest_started_at
        super().__init__(
            f"Decision outcome {outcome_id} validated_at {validated_at.isoformat()} precedes "
            f"earliest linked action start {earliest_started_at.isoformat()}."
        )


class DecisionLifecycleService:
    """Canonical owner of the minimal Decision lifecycle projection."""

    def __init__(
        self,
        decision_repository: DecisionRepository,
        acceptance_repository: DecisionAcceptanceRepository,
        action_repository: DecisionActionRepository,
        outcome_repository: DecisionOutcomeRepository,
    ) -> None:
        self._decision_repository = decision_repository
        self._acceptance_repository = acceptance_repository
        self._action_repository = action_repository
        self._outcome_repository = outcome_repository

    def state(self, decision_id: UUID) -> DecisionLifecycleState:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionLifecycleDecisionNotFoundError(decision_id)

        acceptances = [
            acceptance
            for acceptance in self._acceptance_repository.load_all()
            if acceptance.decision_id == decision_id
        ]
        if len(acceptances) > 1:
            raise DecisionLifecycleMultipleAcceptancesError(decision_id)

        all_actions = self._action_repository.load_all()
        actions = [action for action in all_actions if action.decision_id == decision_id]
        acceptance_id = acceptances[0].id if acceptances else None
        for action in actions:
            if action.acceptance_id != acceptance_id:
                raise DecisionLifecycleActionAcceptanceMismatchError(
                    action_id=action.id,
                    expected_acceptance_id=acceptance_id,
                    actual_acceptance_id=action.acceptance_id,
                )

        outcomes = [
            outcome
            for outcome in self._outcome_repository.load_all()
            if outcome.decision_id == decision_id
        ]
        actions_by_id = {action.id: action for action in all_actions}
        for outcome in outcomes:
            if outcome.acceptance_id != acceptance_id:
                raise DecisionLifecycleOutcomeAcceptanceMismatchError(
                    outcome.id, acceptance_id, outcome.acceptance_id
                )
            linked_actions = []
            for action_id in outcome.action_ids:
                linked_action = actions_by_id.get(action_id)
                if linked_action is None:
                    raise DecisionLifecycleOutcomeActionNotFoundError(outcome.id, action_id)
                if linked_action.decision_id != decision_id:
                    raise DecisionLifecycleOutcomeActionDecisionMismatchError(
                        outcome.id, action_id, decision_id, linked_action.decision_id
                    )
                if linked_action.acceptance_id != outcome.acceptance_id:
                    raise DecisionLifecycleOutcomeActionAcceptanceMismatchError(
                        outcome.id,
                        action_id,
                        outcome.acceptance_id,
                        linked_action.acceptance_id,
                    )
                linked_actions.append(linked_action)
            earliest_started_at = min(action.started_at for action in linked_actions)
            if outcome.validated_at < earliest_started_at:
                raise DecisionLifecycleOutcomeValidationBeforeActionError(
                    outcome.id, outcome.validated_at, earliest_started_at
                )

        if outcomes:
            latest = max(outcomes, key=lambda item: (item.validated_at, str(item.id)))
            return {
                "succeeded": DecisionLifecycleState.SUCCEEDED,
                "failed": DecisionLifecycleState.FAILED,
                "partial": DecisionLifecycleState.PARTIAL,
                "unknown": DecisionLifecycleState.OUTCOME_UNKNOWN,
            }[latest.result.value]

        if actions:
            return DecisionLifecycleState.IN_PROGRESS
        if acceptances:
            return DecisionLifecycleState.ACCEPTED
        return DecisionLifecycleState.PROPOSED
