from uuid import UUID

from neural_engine.domain import Decision, EvidenceReference
from neural_engine.ports.decision_repository import DecisionRepository
from neural_engine.ports.observation_repository import ObservationRepository


class DecisionError(Exception):
    """Base error for Decision service failures."""


class DecisionNotFoundError(DecisionError):
    """Raised when a requested Decision does not exist."""

    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision not found: {decision_id}")


class DecisionObservationNotFoundError(DecisionError):
    """Raised when a Decision references an unknown Observation."""

    def __init__(self, observation_id: UUID) -> None:
        self.observation_id = observation_id
        super().__init__(f"Observation not found: {observation_id}")


class DecisionSupersededNotFoundError(DecisionError):
    """Raised when a Decision supersedes an unknown Decision."""

    def __init__(self, decision_id: UUID) -> None:
        self.decision_id = decision_id
        super().__init__(f"Superseded Decision not found: {decision_id}")


class DecisionSupersededProjectMismatchError(DecisionError):
    """Raised when a superseded Decision belongs to another project."""

    def __init__(
        self,
        decision_id: UUID,
        expected_project_key: str,
        actual_project_key: str,
    ) -> None:
        self.decision_id = decision_id
        self.expected_project_key = expected_project_key
        self.actual_project_key = actual_project_key
        super().__init__(
            f"Superseded Decision {decision_id} belongs to project {actual_project_key}, "
            f"expected {expected_project_key}."
        )


class DecisionIdempotencyConflictError(DecisionError):
    """Raised when an idempotency key is reused with a different payload."""

    def __init__(self, project_key: str, idempotency_key: str) -> None:
        self.project_key = project_key
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Decision idempotency key {idempotency_key!r} already exists for project "
            f"{project_key!r} with a different payload."
        )


class DecisionProjectKeyRequiredError(DecisionError):
    """Raised when a project filter is blank."""

    def __init__(self) -> None:
        super().__init__("Decision project filter must not be blank.")


class DecisionService:
    """Application service for proposed Decisions."""

    def __init__(
        self,
        decision_repository: DecisionRepository,
        observation_repository: ObservationRepository,
    ) -> None:
        self._decision_repository = decision_repository
        self._observation_repository = observation_repository

    def add(
        self,
        project_key: str,
        title: str,
        objective: str,
        context_summary: str,
        alternatives: list[str],
        proposed_option: str,
        rationale: str,
        proposed_by: str,
        idempotency_key: str,
        observation_ids: list[UUID] | None = None,
        evidence_references: list[EvidenceReference] | None = None,
        supersedes_decision_id: UUID | None = None,
        tags: list[str] | None = None,
    ) -> Decision:
        candidate = Decision(
            project_key=project_key,
            title=title,
            objective=objective,
            context_summary=context_summary,
            alternatives=tuple(alternatives),
            proposed_option=proposed_option,
            rationale=rationale,
            observation_ids=tuple(observation_ids or []),
            evidence_references=tuple(evidence_references or []),
            proposed_by=proposed_by,
            supersedes_decision_id=supersedes_decision_id,
            idempotency_key=idempotency_key,
            tags=tuple(tags or []),
        )

        self._validate_observations(candidate.observation_ids)
        self._validate_superseded_decision(candidate)

        decisions = self._decision_repository.load_all()
        existing = self._find_by_idempotency_key(decisions, candidate)
        if existing is not None:
            if self._semantic_payload(existing) == self._semantic_payload(candidate):
                return existing

            raise DecisionIdempotencyConflictError(
                project_key=candidate.project_key,
                idempotency_key=candidate.idempotency_key,
            )

        self._decision_repository.save(candidate)
        return candidate

    def list_decisions(self, project_key: str | None = None) -> list[Decision]:
        decisions = self._decision_repository.load_all()
        if project_key is None:
            return decisions

        normalized_project_key = project_key.strip()
        if not normalized_project_key:
            raise DecisionProjectKeyRequiredError()

        return [
            decision for decision in decisions if decision.project_key == normalized_project_key
        ]

    def show(self, decision_id: UUID) -> Decision:
        decision = self._decision_repository.get_by_id(decision_id)
        if decision is None:
            raise DecisionNotFoundError(decision_id)

        return decision

    def _validate_observations(self, observation_ids: tuple[UUID, ...]) -> None:
        for observation_id in observation_ids:
            if self._observation_repository.get_by_id(observation_id) is None:
                raise DecisionObservationNotFoundError(observation_id)

    def _validate_superseded_decision(self, candidate: Decision) -> None:
        if candidate.supersedes_decision_id is None:
            return

        superseded = self._decision_repository.get_by_id(candidate.supersedes_decision_id)
        if superseded is None:
            raise DecisionSupersededNotFoundError(candidate.supersedes_decision_id)

        if superseded.project_key != candidate.project_key:
            raise DecisionSupersededProjectMismatchError(
                decision_id=superseded.id,
                expected_project_key=candidate.project_key,
                actual_project_key=superseded.project_key,
            )

    @staticmethod
    def _find_by_idempotency_key(
        decisions: list[Decision],
        candidate: Decision,
    ) -> Decision | None:
        for decision in decisions:
            if (
                decision.project_key == candidate.project_key
                and decision.idempotency_key == candidate.idempotency_key
            ):
                return decision

        return None

    @staticmethod
    def _semantic_payload(decision: Decision) -> dict[str, object]:
        payload = decision.model_dump(mode="json", exclude={"id", "created_at"})
        payload["evidence_references"] = [
            evidence.model_dump(mode="json", exclude={"captured_at"})
            for evidence in decision.evidence_references
        ]
        return payload
