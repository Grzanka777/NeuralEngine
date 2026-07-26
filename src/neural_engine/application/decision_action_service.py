from datetime import datetime
from uuid import UUID

from neural_engine.application.playbook_run_service import PlaybookRunReader
from neural_engine.domain import DecisionAction, EvidenceReference
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_repository import DecisionRepository


class DecisionActionError(Exception):
    """Base error for Decision action service failures."""


class DecisionActionDecisionNotFoundError(DecisionActionError):
    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision not found: {decision_id}")


class DecisionActionAcceptanceNotFoundError(DecisionActionError):
    def __init__(self, acceptance_id: UUID) -> None:
        self.acceptance_id = acceptance_id
        super().__init__(f"Decision acceptance not found: {acceptance_id}")


class DecisionActionAcceptanceMismatchError(DecisionActionError):
    def __init__(
        self,
        acceptance_id: UUID,
        expected_decision_id: UUID,
        actual_decision_id: UUID,
    ) -> None:
        self.acceptance_id = acceptance_id
        self.expected_decision_id = expected_decision_id
        self.actual_decision_id = actual_decision_id
        super().__init__(
            f"Decision acceptance {acceptance_id} belongs to Decision {actual_decision_id}, "
            f"expected {expected_decision_id}."
        )


class DecisionActionPlaybookRunNotFoundError(DecisionActionError):
    def __init__(self, playbook_run_id: UUID) -> None:
        self.playbook_run_id = playbook_run_id
        super().__init__(f"Playbook run not found: {playbook_run_id}")


class DecisionActionNotFoundError(DecisionActionError):
    def __init__(self, action_id: UUID) -> None:
        self.action_id = action_id
        super().__init__(f"Decision action not found: {action_id}")


class DecisionActionIdempotencyConflictError(DecisionActionError):
    def __init__(self, decision_id: UUID, idempotency_key: str) -> None:
        self.decision_id = decision_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Decision action idempotency key {idempotency_key!r} already exists for "
            f"Decision {decision_id} with a different payload."
        )


class DecisionActionService:
    """Application service for work recorded under accepted Decisions."""

    def __init__(
        self,
        action_repository: DecisionActionRepository,
        decision_repository: DecisionRepository,
        acceptance_repository: DecisionAcceptanceRepository,
        playbook_run_repository: PlaybookRunReader,
    ) -> None:
        self._action_repository = action_repository
        self._decision_repository = decision_repository
        self._acceptance_repository = acceptance_repository
        self._playbook_run_repository = playbook_run_repository

    def add(
        self,
        decision_id: UUID,
        acceptance_id: UUID,
        action_type: str,
        summary: str,
        performed_by: str,
        started_at: datetime,
        idempotency_key: str,
        completed_at: datetime | None = None,
        evidence_references: list[EvidenceReference] | None = None,
        playbook_run_id: UUID | None = None,
        tags: list[str] | None = None,
    ) -> DecisionAction:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionActionDecisionNotFoundError(decision_id)

        acceptance = self._acceptance_repository.get_by_id(acceptance_id)
        if acceptance is None:
            raise DecisionActionAcceptanceNotFoundError(acceptance_id)
        if acceptance.decision_id != decision_id:
            raise DecisionActionAcceptanceMismatchError(
                acceptance_id=acceptance_id,
                expected_decision_id=decision_id,
                actual_decision_id=acceptance.decision_id,
            )

        if (
            playbook_run_id is not None
            and self._playbook_run_repository.get_by_id(playbook_run_id) is None
        ):
            raise DecisionActionPlaybookRunNotFoundError(playbook_run_id)

        candidate = DecisionAction(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            action_type=action_type,
            summary=summary,
            performed_by=performed_by,
            started_at=started_at,
            completed_at=completed_at,
            evidence_references=tuple(evidence_references or []),
            playbook_run_id=playbook_run_id,
            idempotency_key=idempotency_key,
            tags=tuple(tags or []),
        )

        actions = self._action_repository.load_all()
        existing = self._find_by_idempotency_key(actions, candidate)
        if existing is not None:
            if self._semantic_payload(existing) == self._semantic_payload(candidate):
                return existing

            raise DecisionActionIdempotencyConflictError(
                decision_id=candidate.decision_id,
                idempotency_key=candidate.idempotency_key,
            )

        self._action_repository.save(candidate)
        return candidate

    def list_for_decision(self, decision_id: UUID) -> list[DecisionAction]:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionActionDecisionNotFoundError(decision_id)

        return [
            action
            for action in self._action_repository.load_all()
            if action.decision_id == decision_id
        ]

    def show(self, action_id: UUID) -> DecisionAction:
        action = self._action_repository.get_by_id(action_id)
        if action is None:
            raise DecisionActionNotFoundError(action_id)

        return action

    @staticmethod
    def _find_by_idempotency_key(
        actions: list[DecisionAction],
        candidate: DecisionAction,
    ) -> DecisionAction | None:
        return next(
            (
                action
                for action in actions
                if action.decision_id == candidate.decision_id
                and action.idempotency_key == candidate.idempotency_key
            ),
            None,
        )

    @staticmethod
    def _semantic_payload(action: DecisionAction) -> dict[str, object]:
        payload = action.model_dump(mode="json", exclude={"id", "recorded_at"})
        payload["evidence_references"] = [
            evidence.model_dump(mode="json", exclude={"captured_at"})
            for evidence in action.evidence_references
        ]
        return payload
