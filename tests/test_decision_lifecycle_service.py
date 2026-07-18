from datetime import UTC, datetime
from uuid import UUID

import pytest

from neural_engine.application.decision_lifecycle_service import (
    DecisionLifecycleActionAcceptanceMismatchError,
    DecisionLifecycleDecisionNotFoundError,
    DecisionLifecycleMultipleAcceptancesError,
    DecisionLifecycleOutcomeActionNotFoundError,
    DecisionLifecycleService,
    DecisionLifecycleState,
)
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
)
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
from neural_engine.ports.decision_repository import DecisionRepository


class FakeDecisionRepository(DecisionRepository):
    def __init__(self, decisions: list[Decision]) -> None:
        self.decisions = decisions

    def save(self, decision: Decision) -> None:
        self.decisions.append(decision)

    def load_all(self) -> list[Decision]:
        return self.decisions

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        return next((decision for decision in self.decisions if decision.id == decision_id), None)


class FakeAcceptanceRepository(DecisionAcceptanceRepository):
    def __init__(self, acceptances: list[DecisionAcceptance]) -> None:
        self.acceptances = acceptances

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
    def __init__(self, actions: list[DecisionAction]) -> None:
        self.actions = actions

    def save(self, action: DecisionAction) -> None:
        self.actions.append(action)

    def load_all(self) -> list[DecisionAction]:
        return self.actions

    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        return next((action for action in self.actions if action.id == action_id), None)


class FakeOutcomeRepository(DecisionOutcomeRepository):
    def __init__(self, outcomes: list[DecisionOutcome]) -> None:
        self.outcomes = outcomes

    def save(self, outcome: DecisionOutcome) -> None:
        self.outcomes.append(outcome)

    def load_all(self) -> list[DecisionOutcome]:
        return self.outcomes

    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        return next((outcome for outcome in self.outcomes if outcome.id == outcome_id), None)


def make_decision() -> Decision:
    return Decision(
        project_key="NeuralEngine",
        title="Project lifecycle state",
        objective="Derive one canonical state",
        context_summary="Decision records are immutable.",
        alternatives=("Canonical service", "Duplicate replay"),
        proposed_option="Canonical service",
        rationale="One owner prevents drift.",
        proposed_by="architecture-review",
        idempotency_key="decision-state",
    )


def make_acceptance(decision_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "accepted_by": "owner",
        "reason": "Approved.",
        "idempotency_key": "acceptance-state",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def make_action(decision_id: UUID, acceptance_id: UUID, **updates: object) -> DecisionAction:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_type": "implementation",
        "summary": "Work was performed.",
        "performed_by": "codex",
        "started_at": datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        "idempotency_key": "action-state",
    }
    values.update(updates)
    return DecisionAction.model_validate(values)


def make_outcome(
    decision_id: UUID,
    acceptance_id: UUID,
    action_ids: tuple[UUID, ...],
    **updates: object,
) -> DecisionOutcome:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_ids": action_ids,
        "result": DecisionOutcomeResult.SUCCEEDED,
        "summary": "Validation passed.",
        "validated_by": "pytest",
        "validated_at": datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        "idempotency_key": "outcome-state",
    }
    values.update(updates)
    return DecisionOutcome.model_validate(values)


def make_service(
    decisions: list[Decision],
    acceptances: list[DecisionAcceptance] | None = None,
    actions: list[DecisionAction] | None = None,
    outcomes: list[DecisionOutcome] | None = None,
) -> DecisionLifecycleService:
    return DecisionLifecycleService(
        FakeDecisionRepository(decisions),
        FakeAcceptanceRepository(acceptances or []),
        FakeActionRepository(actions or []),
        FakeOutcomeRepository(outcomes or []),
    )


def test_state_rejects_missing_decision() -> None:
    missing = UUID("11111111-1111-1111-1111-111111111111")
    with pytest.raises(DecisionLifecycleDecisionNotFoundError):
        make_service([]).state(missing)


def test_state_is_proposed_without_acceptance_or_action() -> None:
    decision = make_decision()
    assert make_service([decision]).state(decision.id) is DecisionLifecycleState.PROPOSED


def test_state_is_accepted_with_acceptance_and_no_action() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    assert (
        make_service([decision], [acceptance]).state(decision.id) is DecisionLifecycleState.ACCEPTED
    )


def test_state_is_in_progress_with_valid_action() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    action = make_action(decision.id, acceptance.id)
    assert (
        make_service([decision], [acceptance], [action]).state(decision.id)
        is DecisionLifecycleState.IN_PROGRESS
    )


def test_multiple_actions_remain_in_progress() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    first = make_action(decision.id, acceptance.id)
    second = make_action(decision.id, acceptance.id, idempotency_key="action-2")

    state = make_service([decision], [acceptance], [second, first]).state(decision.id)

    assert state is DecisionLifecycleState.IN_PROGRESS
    assert {item.value for item in DecisionLifecycleState} == {
        "proposed",
        "accepted",
        "in_progress",
        "succeeded",
        "failed",
        "partial",
        "outcome_unknown",
    }


def test_invalid_action_acceptance_relation_fails_visibly() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    action = make_action(
        decision.id,
        UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(DecisionLifecycleActionAcceptanceMismatchError):
        make_service([decision], [acceptance], [action]).state(decision.id)


def test_multiple_persisted_acceptances_fail_visibly() -> None:
    decision = make_decision()
    first = make_acceptance(decision.id)
    second = make_acceptance(decision.id, idempotency_key="acceptance-2")

    with pytest.raises(DecisionLifecycleMultipleAcceptancesError):
        make_service([decision], [first, second]).state(decision.id)


@pytest.mark.parametrize(
    ("result", "state"),
    [
        (DecisionOutcomeResult.SUCCEEDED, DecisionLifecycleState.SUCCEEDED),
        (DecisionOutcomeResult.FAILED, DecisionLifecycleState.FAILED),
        (DecisionOutcomeResult.PARTIAL, DecisionLifecycleState.PARTIAL),
        (DecisionOutcomeResult.UNKNOWN, DecisionLifecycleState.OUTCOME_UNKNOWN),
    ],
)
def test_latest_outcome_derives_extended_state(
    result: DecisionOutcomeResult, state: DecisionLifecycleState
) -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    action = make_action(decision.id, acceptance.id)
    earlier = make_outcome(
        decision.id,
        acceptance.id,
        (action.id,),
        id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        result=DecisionOutcomeResult.FAILED,
        validated_at=datetime(2026, 7, 17, 10, 30, tzinfo=UTC),
    )
    latest = make_outcome(
        decision.id,
        acceptance.id,
        (action.id,),
        id=UUID("00000000-0000-0000-0000-000000000001"),
        result=result,
        idempotency_key="latest",
    )

    assert (
        make_service([decision], [acceptance], [action], [latest, earlier]).state(decision.id)
        is state
    )


def test_latest_outcome_uses_id_as_stable_timestamp_tie_breaker() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    action = make_action(decision.id, acceptance.id)
    low = make_outcome(
        decision.id,
        acceptance.id,
        (action.id,),
        id=UUID("00000000-0000-0000-0000-000000000001"),
        result=DecisionOutcomeResult.FAILED,
    )
    high = make_outcome(
        decision.id,
        acceptance.id,
        (action.id,),
        id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        result=DecisionOutcomeResult.PARTIAL,
        idempotency_key="high",
    )

    state = make_service([decision], [acceptance], [action], [high, low]).state(decision.id)

    assert state is DecisionLifecycleState.PARTIAL


def test_outcome_with_missing_action_fails_visibly() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    missing_action_id = UUID("11111111-1111-1111-1111-111111111111")
    outcome = make_outcome(decision.id, acceptance.id, (missing_action_id,))

    with pytest.raises(DecisionLifecycleOutcomeActionNotFoundError):
        make_service([decision], [acceptance], outcomes=[outcome]).state(decision.id)
