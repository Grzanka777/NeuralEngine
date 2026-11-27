from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from neural_engine.application.decision_lifecycle_service import (
    DecisionLifecycleService,
    DecisionLifecycleState,
)
from neural_engine.application.decision_service import (
    DecisionIdempotencyConflictError,
    DecisionNotFoundError,
    DecisionObservationNotFoundError,
    DecisionProjectKeyRequiredError,
    DecisionService,
    DecisionSupersededNotFoundError,
    DecisionSupersededProjectMismatchError,
    DecisionSupersessionCycleError,
)
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    EvidenceReference,
    Observation,
)
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
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


class FakeAcceptanceRepository(DecisionAcceptanceRepository):
    def __init__(self, acceptances: list[DecisionAcceptance] | None = None) -> None:
        self.acceptances = acceptances or []

    def save(self, acceptance: DecisionAcceptance) -> None:
        self.acceptances.append(acceptance)

    def load_all(self) -> list[DecisionAcceptance]:
        return self.acceptances

    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        return next(
            (acceptance for acceptance in self.acceptances if acceptance.id == acceptance_id),
            None,
        )


class FakeActionRepository(DecisionActionRepository):
    def __init__(self, actions: list[DecisionAction] | None = None) -> None:
        self.actions = actions or []

    def save(self, action: DecisionAction) -> None:
        self.actions.append(action)

    def load_all(self) -> list[DecisionAction]:
        return self.actions

    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        return next((action for action in self.actions if action.id == action_id), None)


class FakeOutcomeRepository(DecisionOutcomeRepository):
    def __init__(self, outcomes: list[DecisionOutcome] | None = None) -> None:
        self.outcomes = outcomes or []

    def save(self, outcome: DecisionOutcome) -> None:
        self.outcomes.append(outcome)

    def load_all(self) -> list[DecisionOutcome]:
        return self.outcomes

    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        return next((outcome for outcome in self.outcomes if outcome.id == outcome_id), None)


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


# --- Tests for get_active_decisions ---


def test_get_active_decisions_single_decision() -> None:
    decision = make_decision("NeuralEngine", "dec-1", title="Standalone Decision")
    service, _, _ = make_service([decision])

    active = service.get_active_decisions("NeuralEngine")

    assert active == [decision]


def test_get_active_decisions_linear_supersession_chain() -> None:
    d1 = make_decision("NeuralEngine", "dec-1", title="D1")
    d2 = make_decision("NeuralEngine", "dec-2", title="D2", supersedes_decision_id=d1.id)
    d3 = make_decision("NeuralEngine", "dec-3", title="D3", supersedes_decision_id=d2.id)
    service, _, _ = make_service([d1, d2, d3])

    active = service.get_active_decisions("NeuralEngine")

    assert active == [d3]


def test_get_active_decisions_multiple_independent_lineages() -> None:
    base_time = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    # Lineage 1: d1 -> d2
    d1 = make_decision("NeuralEngine", "l1-1", title="L1-1", created_at=base_time)
    d2 = make_decision(
        "NeuralEngine",
        "l1-2",
        title="L1-2",
        supersedes_decision_id=d1.id,
        created_at=base_time + timedelta(hours=2),
    )
    # Lineage 2: d3 alone
    d3 = make_decision(
        "NeuralEngine", "l2-1", title="L2-1", created_at=base_time + timedelta(hours=1)
    )
    service, _, _ = make_service([d2, d1, d3])

    active = service.get_active_decisions("NeuralEngine")

    assert active == [d3, d2]


def test_get_active_decisions_multiple_successor_branches() -> None:
    base_time = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    d1 = make_decision("NeuralEngine", "root", title="Root", created_at=base_time)
    d2 = make_decision(
        "NeuralEngine",
        "branch-a",
        title="Branch A",
        supersedes_decision_id=d1.id,
        created_at=base_time + timedelta(hours=1),
    )
    d3 = make_decision(
        "NeuralEngine",
        "branch-b",
        title="Branch B",
        supersedes_decision_id=d1.id,
        created_at=base_time + timedelta(hours=2),
    )
    service, _, _ = make_service([d1, d2, d3])

    active = service.get_active_decisions("NeuralEngine")

    assert active == [d2, d3]


def test_get_active_decisions_superseded_with_existing_acceptance() -> None:
    d1 = make_decision("NeuralEngine", "dec-old", title="Old Decision")
    d2 = make_decision(
        "NeuralEngine", "dec-new", title="New Decision", supersedes_decision_id=d1.id
    )

    acceptance = DecisionAcceptance(
        decision_id=d1.id,
        accepted_by="lead-architect",
        reason="Approved old decision",
        idempotency_key="acc-old",
    )

    decision_repo = FakeDecisionRepository([d1, d2])
    acceptance_repo = FakeAcceptanceRepository([acceptance])
    action_repo = FakeActionRepository([])
    outcome_repo = FakeOutcomeRepository([])

    decision_service = DecisionService(decision_repo, FakeObservationRepository())
    lifecycle_service = DecisionLifecycleService(
        decision_repo, acceptance_repo, action_repo, outcome_repo
    )

    # Projection returns only the new decision
    assert decision_service.get_active_decisions("NeuralEngine") == [d2]

    # Historical lifecycle state of d1 remains ACCEPTED
    assert lifecycle_service.state(d1.id) == DecisionLifecycleState.ACCEPTED

    # Lifecycle state of new decision d2 remains PROPOSED
    assert lifecycle_service.state(d2.id) == DecisionLifecycleState.PROPOSED


CYCLE_IDS = tuple(UUID(int=value) for value in (1, 2, 3, 4))


@pytest.mark.parametrize("order", [(0, 1, 2, 3), (3, 2, 1, 0), (1, 3, 0, 2), (2, 0, 3, 1)])
def test_get_active_decisions_cycle_ids_are_canonical_for_any_load_order(
    order: tuple[int, ...],
) -> None:
    id1, id2, id3, tail_id = CYCLE_IDS
    # Traversal (successor -> predecessor): id1 -> id3 -> id2 -> id1; tail -> id1 enters the cycle.
    decisions = [
        make_decision("NeuralEngine", "c1", id=id1, supersedes_decision_id=id3),
        make_decision("NeuralEngine", "c2", id=id2, supersedes_decision_id=id1),
        make_decision("NeuralEngine", "c3", id=id3, supersedes_decision_id=id2),
        make_decision("NeuralEngine", "tail", id=tail_id, supersedes_decision_id=id1),
    ]
    service, _, _ = make_service([decisions[index] for index in order])

    with pytest.raises(DecisionSupersessionCycleError) as error:
        service.get_active_decisions("NeuralEngine")

    assert error.value.cycle_ids == (id1, id3, id2)
    assert tail_id not in error.value.cycle_ids
    assert str(error.value) == f"Decision supersession cycle detected: {id1}, {id3}, {id2}"


def test_get_active_decisions_missing_predecessor_reference_fail_closed() -> None:
    missing_id = UUID("44444444-4444-4444-4444-444444444444")
    d1 = make_decision("NeuralEngine", "dec-1", supersedes_decision_id=missing_id)
    service, _, _ = make_service([d1])

    with pytest.raises(DecisionSupersededNotFoundError) as error:
        service.get_active_decisions("NeuralEngine")

    assert error.value.decision_id == missing_id


def test_get_active_decisions_cross_project_reference_fail_closed() -> None:
    d_other = make_decision("OtherProject", "dec-other")
    d_local = make_decision("NeuralEngine", "dec-local", supersedes_decision_id=d_other.id)
    service, _, _ = make_service([d_other, d_local])

    with pytest.raises(DecisionSupersededProjectMismatchError) as error:
        service.get_active_decisions("NeuralEngine")

    assert error.value.decision_id == d_other.id
    assert error.value.expected_project_key == "NeuralEngine"
    assert error.value.actual_project_key == "OtherProject"


def test_get_active_decisions_empty_project() -> None:
    d_other = make_decision("OtherProject", "dec-other")
    service, _, _ = make_service([d_other])

    assert service.get_active_decisions("NeuralEngine") == []
    assert service.get_active_decisions("NonExistent") == []


def test_get_active_decisions_blank_project_key_raises() -> None:
    service, _, _ = make_service()

    with pytest.raises(DecisionProjectKeyRequiredError):
        service.get_active_decisions("")

    with pytest.raises(DecisionProjectKeyRequiredError):
        service.get_active_decisions("   ")


def test_get_active_decisions_deterministic_result_ordering() -> None:
    t1 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    # Two decisions with same created_at, different IDs
    id_a = UUID("00000000-0000-0000-0000-000000000001")
    id_b = UUID("00000000-0000-0000-0000-000000000002")

    da = make_decision("NeuralEngine", "a", id=id_a, created_at=t1)
    db = make_decision("NeuralEngine", "b", id=id_b, created_at=t1)
    dc = make_decision("NeuralEngine", "c", created_at=t2)

    # Active decisions must be sorted by (created_at, str(id)) regardless of load order
    service1, _, _ = make_service([dc, db, da])
    service2, _, _ = make_service([da, dc, db])

    result1 = service1.get_active_decisions("NeuralEngine")
    result2 = service2.get_active_decisions("NeuralEngine")

    expected = [da, db, dc]
    assert result1 == expected
    assert result2 == expected


def test_get_active_decisions_does_not_mutate_repository_state() -> None:
    base_time = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    superseded = make_decision("NeuralEngine", "dec-old", created_at=base_time)
    successor = make_decision(
        "NeuralEngine",
        "dec-new",
        supersedes_decision_id=superseded.id,
        created_at=base_time + timedelta(hours=1),
    )
    service, repository, _ = make_service([superseded, successor])
    before = list(repository.decisions)

    assert service.get_active_decisions("NeuralEngine") == [successor]

    assert repository.save_calls == []
    assert repository.load_all_calls > 0
    assert repository.decisions == before


def test_get_active_decisions_ignores_foreign_project_successor() -> None:
    local = make_decision("NeuralEngine", "local")
    foreign = make_decision("OtherProject", "foreign", supersedes_decision_id=local.id)
    service, _, _ = make_service([local, foreign])

    assert service.get_active_decisions("NeuralEngine") == [local]


def test_get_active_decisions_ignores_corrupted_lineage_in_other_project() -> None:
    local = make_decision("NeuralEngine", "local")
    other_a = make_decision(
        "OtherProject", "o-a", id=CYCLE_IDS[0], supersedes_decision_id=CYCLE_IDS[1]
    )
    other_b = make_decision(
        "OtherProject", "o-b", id=CYCLE_IDS[1], supersedes_decision_id=CYCLE_IDS[0]
    )
    other_dangling = make_decision("OtherProject", "o-d", supersedes_decision_id=uuid4())
    service, _, _ = make_service([other_a, local, other_b, other_dangling])

    assert service.get_active_decisions("NeuralEngine") == [local]
    with pytest.raises(DecisionSupersededNotFoundError):
        service.get_active_decisions("OtherProject")


def test_get_active_decisions_fails_closed_for_corruption_beside_valid_lineage() -> None:
    valid = make_decision("NeuralEngine", "valid")
    dangling = make_decision("NeuralEngine", "dangling", supersedes_decision_id=uuid4())
    other = make_decision("OtherProject", "other")
    service, _, _ = make_service([valid, other, dangling])

    with pytest.raises(DecisionSupersededNotFoundError):
        service.get_active_decisions("NeuralEngine")
