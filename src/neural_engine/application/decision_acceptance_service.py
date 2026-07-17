from uuid import UUID

from neural_engine.domain import DecisionAcceptance, EvidenceReference
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_repository import DecisionRepository


class DecisionAcceptanceError(Exception):
    """Base error for Decision acceptance service failures."""


class DecisionAcceptanceDecisionNotFoundError(DecisionAcceptanceError):
    """Raised when an acceptance references an unknown Decision."""

    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision not found: {decision_id}")


class DecisionAcceptanceNotFoundError(DecisionAcceptanceError):
    """Raised when a requested Decision acceptance does not exist."""

    def __init__(self, acceptance_id: UUID) -> None:
        self.acceptance_id = acceptance_id
        super().__init__(f"Decision acceptance not found: {acceptance_id}")


class DecisionAlreadyAcceptedError(DecisionAcceptanceError):
    """Raised when a Decision already has a distinct acceptance."""

    def __init__(self, decision_id: UUID, acceptance_id: UUID) -> None:
        self.decision_id = decision_id
        self.acceptance_id = acceptance_id
        super().__init__(
            f"Decision {decision_id} is already accepted by acceptance {acceptance_id}."
        )


class DecisionAcceptanceIdempotencyConflictError(DecisionAcceptanceError):
    """Raised when an acceptance key is reused with a different payload."""

    def __init__(self, decision_id: UUID, idempotency_key: str) -> None:
        self.decision_id = decision_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Decision acceptance idempotency key {idempotency_key!r} already exists for "
            f"Decision {decision_id} with a different payload."
        )


class DecisionAcceptanceService:
    """Application service for explicit Decision authorization."""

    def __init__(
        self,
        acceptance_repository: DecisionAcceptanceRepository,
        decision_repository: DecisionRepository,
    ) -> None:
        self._acceptance_repository = acceptance_repository
        self._decision_repository = decision_repository

    def accept(
        self,
        decision_id: UUID,
        accepted_by: str,
        reason: str,
        idempotency_key: str,
        evidence_references: list[EvidenceReference] | None = None,
        tags: list[str] | None = None,
    ) -> DecisionAcceptance:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionAcceptanceDecisionNotFoundError(decision_id)

        candidate = DecisionAcceptance(
            decision_id=decision_id,
            accepted_by=accepted_by,
            reason=reason,
            evidence_references=tuple(evidence_references or []),
            idempotency_key=idempotency_key,
            tags=tuple(tags or []),
        )
        acceptances = self._acceptance_repository.load_all()

        existing_for_key = self._find_by_idempotency_key(acceptances, candidate)
        if existing_for_key is not None:
            if self._semantic_payload(existing_for_key) == self._semantic_payload(candidate):
                return existing_for_key

            raise DecisionAcceptanceIdempotencyConflictError(
                decision_id=candidate.decision_id,
                idempotency_key=candidate.idempotency_key,
            )

        existing_for_decision = next(
            (
                acceptance
                for acceptance in acceptances
                if acceptance.decision_id == candidate.decision_id
            ),
            None,
        )
        if existing_for_decision is not None:
            raise DecisionAlreadyAcceptedError(
                decision_id=candidate.decision_id,
                acceptance_id=existing_for_decision.id,
            )

        self._acceptance_repository.save(candidate)
        return candidate

    def list_for_decision(self, decision_id: UUID) -> list[DecisionAcceptance]:
        if self._decision_repository.get_by_id(decision_id) is None:
            raise DecisionAcceptanceDecisionNotFoundError(decision_id)

        return [
            acceptance
            for acceptance in self._acceptance_repository.load_all()
            if acceptance.decision_id == decision_id
        ]

    def show(self, acceptance_id: UUID) -> DecisionAcceptance:
        acceptance = self._acceptance_repository.get_by_id(acceptance_id)
        if acceptance is None:
            raise DecisionAcceptanceNotFoundError(acceptance_id)

        return acceptance

    @staticmethod
    def _find_by_idempotency_key(
        acceptances: list[DecisionAcceptance],
        candidate: DecisionAcceptance,
    ) -> DecisionAcceptance | None:
        return next(
            (
                acceptance
                for acceptance in acceptances
                if acceptance.decision_id == candidate.decision_id
                and acceptance.idempotency_key == candidate.idempotency_key
            ),
            None,
        )

    @staticmethod
    def _semantic_payload(acceptance: DecisionAcceptance) -> dict[str, object]:
        payload = acceptance.model_dump(mode="json", exclude={"id", "accepted_at"})
        payload["evidence_references"] = [
            evidence.model_dump(mode="json", exclude={"captured_at"})
            for evidence in acceptance.evidence_references
        ]
        return payload
