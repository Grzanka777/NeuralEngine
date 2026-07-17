from enum import StrEnum
from uuid import UUID

from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_repository import DecisionRepository


class DecisionLifecycleState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"


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


class DecisionLifecycleService:
    """Canonical owner of the minimal Decision lifecycle projection."""

    def __init__(
        self,
        decision_repository: DecisionRepository,
        acceptance_repository: DecisionAcceptanceRepository,
        action_repository: DecisionActionRepository,
    ) -> None:
        self._decision_repository = decision_repository
        self._acceptance_repository = acceptance_repository
        self._action_repository = action_repository

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

        actions = [
            action
            for action in self._action_repository.load_all()
            if action.decision_id == decision_id
        ]
        acceptance_id = acceptances[0].id if acceptances else None
        for action in actions:
            if action.acceptance_id != acceptance_id:
                raise DecisionLifecycleActionAcceptanceMismatchError(
                    action_id=action.id,
                    expected_acceptance_id=acceptance_id,
                    actual_acceptance_id=action.acceptance_id,
                )

        if actions:
            return DecisionLifecycleState.IN_PROGRESS
        if acceptances:
            return DecisionLifecycleState.ACCEPTED
        return DecisionLifecycleState.PROPOSED
