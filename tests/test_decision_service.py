from uuid import UUID

import pytest

from neural_engine.application.decision_service import (
    DecisionIdempotencyConflictError,
    DecisionNotFoundError,
    DecisionObservationNotFoundError,
    DecisionProjectKeyRequiredError,
    DecisionService,
    DecisionSupersededNotFoundError,
    DecisionSupersededProjectMismatchError,
)
from neural_engine.domain import Decision, EvidenceReference, Observation
from neural_engine.ports.decision_repository import DecisionRepository
from neural_engine.ports.observation_repository import ObservationRepository


class FakeDecisionRepository(DecisionRepository):
    def __init__(self, decisions: list[Decision] | None = None) -> None:
        self.decisions = decisions or []
        self.save_calls: list[Decision] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []

    def save(self, decision: Decision) -> None:
        self.save_calls.append(decision)
        self.decisions.append(decision)

    def load_all(self) -> list[Decision]:
        self.load_all_calls += 1
        return self.decisions

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        self.requested_ids.append(decision_id)
        return next((decision for decision in self.decisions if decision.id == decision_id), None)


class FakeObservationRepository(ObservationRepository):
    def __init__(self, observations: list[Observation] | None = None) -> None:
        self.observations = observations or []
        self.requested_ids: list[UUID] = []

    def save(self, observation: Observation) -> None:
        self.observations.append(observation)

    def load_all(self) -> list[Observation]:
        return self.observations

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        self.requested_ids.append(observation_id)
        return next(
            (observation for observation in self.observations if observation.id == observation_id),
            None,
        )


def make_decision(
    project_key: str = "NeuralEngine",
    idempotency_key: str = "decision-1",
    **updates: object,
) -> Decision:
    values: dict[str, object] = {
        "project_key": project_key,
        "title": "Canonical lifecycle ownership",
        "objective": "Keep lifecycle derivation in one service",
        "context_summary": "A duplicate replay implementation was found.",
        "alternatives": ("Delegate to canonical service", "Keep duplicate replay"),
        "proposed_option": "Delegate to canonical service",
        "rationale": "One owner prevents divergence.",
        "proposed_by": "architecture-review",
        "idempotency_key": idempotency_key,
    }
    values.update(updates)
    return Decision.model_validate(values)


def make_service(
    decisions: list[Decision] | None = None,
    observations: list[Observation] | None = None,
) -> tuple[DecisionService, FakeDecisionRepository, FakeObservationRepository]:
    decision_repository = FakeDecisionRepository(decisions)
    observation_repository = FakeObservationRepository(observations)
    return (
        DecisionService(decision_repository, observation_repository),
        decision_repository,
        observation_repository,
    )


def add_decision(
    service: DecisionService,
    **updates: object,
) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Canonical lifecycle ownership",
        "objective": "Keep lifecycle derivation in one service",
        "context_summary": "A duplicate replay implementation was found.",
        "alternatives": ["Delegate to canonical service", "Keep duplicate replay"],
        "proposed_option": "Delegate to canonical service",
        "rationale": "One owner prevents divergence.",
        "proposed_by": "architecture-review",
        "idempotency_key": "decision-1",
    }
    values.update(updates)
    return service.add(**values)  # type: ignore[arg-type]


def test_add_validates_observations_and_persists_decision() -> None:
    observation = Observation(content="Duplicate lifecycle replay found")
    service, decision_repository, observation_repository = make_service(observations=[observation])
    evidence = EvidenceReference(kind="agent_review", locator="review:decision")

    decision = add_decision(
        service,
        observation_ids=[observation.id],
        evidence_references=[evidence],
        tags=[" architecture ", "review"],
    )

    assert decision_repository.save_calls == [decision]
    assert observation_repository.requested_ids == [observation.id]
    assert decision.observation_ids == (observation.id,)
    assert decision.evidence_references == (evidence,)
    assert decision.tags == ("architecture", "review")


def test_add_raises_for_missing_observation_without_writing() -> None:
    missing_id = UUID("11111111-1111-1111-1111-111111111111")
    service, decision_repository, observation_repository = make_service()

    with pytest.raises(DecisionObservationNotFoundError) as error:
        add_decision(service, observation_ids=[missing_id])

    assert error.value.observation_id == missing_id
    assert observation_repository.requested_ids == [missing_id]
    assert decision_repository.load_all_calls == 0
    assert decision_repository.save_calls == []


def test_add_raises_for_missing_superseded_decision_without_writing() -> None:
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    service, decision_repository, _ = make_service()

    with pytest.raises(DecisionSupersededNotFoundError) as error:
        add_decision(service, supersedes_decision_id=missing_id)

    assert error.value.decision_id == missing_id
    assert decision_repository.requested_ids == [missing_id]
    assert decision_repository.load_all_calls == 0
    assert decision_repository.save_calls == []


def test_add_rejects_cross_project_supersession_without_writing() -> None:
    superseded = make_decision(project_key="OtherProject")
    service, decision_repository, _ = make_service([superseded])

    with pytest.raises(DecisionSupersededProjectMismatchError) as error:
        add_decision(service, supersedes_decision_id=superseded.id)

    assert error.value.decision_id == superseded.id
    assert error.value.expected_project_key == "NeuralEngine"
    assert error.value.actual_project_key == "OtherProject"
    assert decision_repository.save_calls == []


def test_equivalent_idempotent_replay_returns_existing_without_writing() -> None:
    existing = make_decision(
        evidence_references=(EvidenceReference(kind="agent_review", locator="review:1"),),
    )
    service, decision_repository, _ = make_service([existing])

    replayed = add_decision(
        service,
        evidence_references=[EvidenceReference(kind="agent_review", locator="review:1")],
    )

    assert replayed is existing
    assert decision_repository.load_all_calls == 1
    assert decision_repository.save_calls == []


def test_conflicting_idempotency_payload_raises_without_writing() -> None:
    existing = make_decision()
    service, decision_repository, _ = make_service([existing])

    with pytest.raises(DecisionIdempotencyConflictError) as error:
        add_decision(service, rationale="A conflicting rationale")

    assert error.value.project_key == "NeuralEngine"
    assert error.value.idempotency_key == "decision-1"
    assert decision_repository.save_calls == []


def test_same_idempotency_key_is_independent_between_projects() -> None:
    existing = make_decision(project_key="OtherProject")
    service, decision_repository, _ = make_service([existing])

    created = add_decision(service)

    assert created.project_key == "NeuralEngine"
    assert decision_repository.save_calls == [created]


def test_list_decisions_preserves_repository_order_and_filters_by_project() -> None:
    first = make_decision("NeuralEngine", "first", title="First")
    unrelated = make_decision("OtherProject", "other", title="Other")
    second = make_decision("NeuralEngine", "second", title="Second")
    service, _, _ = make_service([second, unrelated, first])

    assert service.list_decisions() == [second, unrelated, first]
    assert service.list_decisions(" NeuralEngine ") == [second, first]


def test_list_decisions_rejects_blank_project_filter() -> None:
    service, _, _ = make_service()

    with pytest.raises(DecisionProjectKeyRequiredError):
        service.list_decisions("  ")


def test_show_returns_existing_decision() -> None:
    decision = make_decision()
    service, decision_repository, _ = make_service([decision])

    assert service.show(decision.id) == decision
    assert decision_repository.requested_ids == [decision.id]


def test_show_raises_for_missing_decision() -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    service, _, _ = make_service()

    with pytest.raises(DecisionNotFoundError) as error:
        service.show(missing_id)

    assert error.value.decision_id == missing_id
