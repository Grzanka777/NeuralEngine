from datetime import UTC, datetime
from uuid import UUID

import pytest

from neural_engine.application.decision_action_service import (
    DecisionActionAcceptanceMismatchError,
    DecisionActionAcceptanceNotFoundError,
    DecisionActionDecisionNotFoundError,
    DecisionActionIdempotencyConflictError,
    DecisionActionNotFoundError,
    DecisionActionPlaybookRunNotFoundError,
    DecisionActionService,
)
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    EvidenceReference,
    PlaybookRun,
)
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_repository import DecisionRepository
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


class FakeActionRepository(DecisionActionRepository):
    def __init__(self, actions: list[DecisionAction] | None = None) -> None:
        self.actions = actions or []
        self.save_calls: list[DecisionAction] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []

    def save(self, action: DecisionAction) -> None:
        self.save_calls.append(action)
        self.actions.append(action)

    def load_all(self) -> list[DecisionAction]:
        self.load_all_calls += 1
        return self.actions

    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        self.requested_ids.append(action_id)
        return next((action for action in self.actions if action.id == action_id), None)


class FakeDecisionRepository(DecisionRepository):
    def __init__(self, decisions: list[Decision] | None = None) -> None:
        self.decisions = decisions or []

    def save(self, decision: Decision) -> None:
        self.decisions.append(decision)

    def load_all(self) -> list[Decision]:
        return self.decisions

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        return next((decision for decision in self.decisions if decision.id == decision_id), None)


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


class FakePlaybookRunRepository(PlaybookRunRepository):
    def __init__(self, runs: list[PlaybookRun] | None = None) -> None:
        self.runs = runs or []

    def save(self, run: PlaybookRun) -> None:
        self.runs.append(run)

    def load_all(self) -> list[PlaybookRun]:
        return self.runs

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        return next((run for run in self.runs if run.id == run_id), None)


def make_decision(**updates: object) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Record implementation action",
        "objective": "Track work under an accepted Decision",
        "context_summary": "The Decision was explicitly accepted.",
        "alternatives": ("Record action", "Leave work implicit"),
        "proposed_option": "Record action",
        "rationale": "Explicit provenance preserves audit history.",
        "proposed_by": "architecture-review",
        "idempotency_key": "decision-1",
    }
    values.update(updates)
    return Decision.model_validate(values)


def make_acceptance(decision_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "accepted_by": "owner",
        "reason": "Approved.",
        "idempotency_key": "acceptance-1",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def make_action(decision_id: UUID, acceptance_id: UUID, **updates: object) -> DecisionAction:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_type": "implementation",
        "summary": "Implemented the action foundation.",
        "performed_by": "codex",
        "started_at": datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        "idempotency_key": "action-1",
    }
    values.update(updates)
    return DecisionAction.model_validate(values)


def make_run() -> PlaybookRun:
    return PlaybookRun(
        playbook_id=UUID("99999999-9999-9999-9999-999999999999"),
        situation="Implement a bounded slice",
        actions_taken=["Implement"],
        outcome="Recorded externally",
        success=True,
    )


def make_service(
    decisions: list[Decision] | None = None,
    acceptances: list[DecisionAcceptance] | None = None,
    actions: list[DecisionAction] | None = None,
    runs: list[PlaybookRun] | None = None,
) -> tuple[DecisionActionService, FakeActionRepository]:
    action_repository = FakeActionRepository(actions)
    return (
        DecisionActionService(
            action_repository,
            FakeDecisionRepository(decisions),
            FakeAcceptanceRepository(acceptances),
            FakePlaybookRunRepository(runs),
        ),
        action_repository,
    )


def add_action(
    service: DecisionActionService,
    decision_id: UUID,
    acceptance_id: UUID,
    **updates: object,
) -> DecisionAction:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_type": "implementation",
        "summary": "Implemented the action foundation.",
        "performed_by": "codex",
        "started_at": datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        "idempotency_key": "action-1",
    }
    values.update(updates)
    return service.add(**values)  # type: ignore[arg-type]


def test_add_validates_relations_and_persists_action_without_mutation() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    revision_id = UUID("34343434-3434-3434-3434-343434343434")
    run = make_run().model_copy(update={"revision_id": revision_id})
    decision_before = decision.model_dump()
    acceptance_before = acceptance.model_dump()
    service, repository = make_service([decision], [acceptance], runs=[run])
    evidence = EvidenceReference(kind="review", locator="review:action")

    action = add_action(
        service,
        decision.id,
        acceptance.id,
        completed_at=datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        evidence_references=[evidence],
        playbook_run_id=run.id,
        tags=["implementation"],
    )

    assert repository.save_calls == [action]
    assert action.playbook_run_id == run.id
    assert run.revision_id == revision_id
    assert decision.model_dump() == decision_before
    assert acceptance.model_dump() == acceptance_before


def test_add_rejects_missing_decision_without_write() -> None:
    missing = UUID("11111111-1111-1111-1111-111111111111")
    service, repository = make_service()

    with pytest.raises(DecisionActionDecisionNotFoundError):
        add_action(service, missing, UUID("22222222-2222-2222-2222-222222222222"))
    assert repository.load_all_calls == 0
    assert repository.save_calls == []


def test_add_rejects_missing_acceptance_without_write() -> None:
    decision = make_decision()
    missing = UUID("22222222-2222-2222-2222-222222222222")
    service, repository = make_service([decision])

    with pytest.raises(DecisionActionAcceptanceNotFoundError):
        add_action(service, decision.id, missing)
    assert repository.save_calls == []


def test_add_rejects_acceptance_for_another_decision() -> None:
    decision = make_decision()
    other = make_decision(idempotency_key="decision-2")
    acceptance = make_acceptance(other.id)
    service, repository = make_service([decision, other], [acceptance])

    with pytest.raises(DecisionActionAcceptanceMismatchError):
        add_action(service, decision.id, acceptance.id)
    assert repository.save_calls == []


def test_add_rejects_missing_optional_playbook_run() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    service, repository = make_service([decision], [acceptance])
    missing = UUID("33333333-3333-3333-3333-333333333333")

    with pytest.raises(DecisionActionPlaybookRunNotFoundError):
        add_action(service, decision.id, acceptance.id, playbook_run_id=missing)
    assert repository.save_calls == []


def test_equivalent_replay_returns_existing() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    existing = make_action(
        decision.id,
        acceptance.id,
        evidence_references=(EvidenceReference(kind="review", locator="review:1"),),
    )
    service, repository = make_service([decision], [acceptance], [existing])

    replay = add_action(
        service,
        decision.id,
        acceptance.id,
        evidence_references=[EvidenceReference(kind="review", locator="review:1")],
    )

    assert replay is existing
    assert repository.save_calls == []


def test_conflicting_idempotency_payload_fails_without_write() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    existing = make_action(decision.id, acceptance.id)
    service, repository = make_service([decision], [acceptance], [existing])

    with pytest.raises(DecisionActionIdempotencyConflictError):
        add_action(service, decision.id, acceptance.id, summary="Different payload")
    assert repository.save_calls == []


def test_multiple_distinct_actions_are_allowed() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    first = make_action(decision.id, acceptance.id)
    service, repository = make_service([decision], [acceptance], [first])

    second = add_action(
        service,
        decision.id,
        acceptance.id,
        summary="Documented the action foundation.",
        idempotency_key="action-2",
    )

    assert repository.save_calls == [second]


def test_list_for_decision_filters_and_preserves_order() -> None:
    decision = make_decision()
    other = make_decision(idempotency_key="decision-2")
    acceptance = make_acceptance(decision.id)
    other_acceptance = make_acceptance(other.id, idempotency_key="acceptance-2")
    first = make_action(decision.id, acceptance.id, idempotency_key="first")
    unrelated = make_action(other.id, other_acceptance.id, idempotency_key="other")
    second = make_action(decision.id, acceptance.id, idempotency_key="second")
    service, _ = make_service(
        [decision, other],
        [acceptance, other_acceptance],
        [second, unrelated, first],
    )

    assert service.list_for_decision(decision.id) == [second, first]


def test_show_returns_existing_and_rejects_missing() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    action = make_action(decision.id, acceptance.id)
    service, _ = make_service([decision], [acceptance], [action])

    assert service.show(action.id) == action
    with pytest.raises(DecisionActionNotFoundError):
        service.show(UUID("44444444-4444-4444-4444-444444444444"))
