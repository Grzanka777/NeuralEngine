from datetime import UTC, datetime
from uuid import UUID

import pytest

from neural_engine.application.decision_outcome_service import (
    DecisionOutcomeAcceptanceMismatchError,
    DecisionOutcomeAcceptanceNotFoundError,
    DecisionOutcomeActionAcceptanceMismatchError,
    DecisionOutcomeActionDecisionMismatchError,
    DecisionOutcomeActionNotFoundError,
    DecisionOutcomeDecisionNotFoundError,
    DecisionOutcomeDuplicateActionError,
    DecisionOutcomeIdempotencyAmbiguityError,
    DecisionOutcomeIdempotencyConflictError,
    DecisionOutcomeNotFoundError,
    DecisionOutcomeService,
    DecisionOutcomeValidationBeforeActionError,
)
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    EvidenceReference,
)
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_action_repository import DecisionActionRepository
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository
from neural_engine.ports.decision_repository import DecisionRepository


class DecisionRepo(DecisionRepository):
    def __init__(self, values: list[Decision]) -> None:
        self.values = values

    def save(self, decision: Decision) -> None:
        self.values.append(decision)

    def load_all(self) -> list[Decision]:
        return self.values

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        return next((item for item in self.values if item.id == decision_id), None)


class AcceptanceRepo(DecisionAcceptanceRepository):
    def __init__(self, values: list[DecisionAcceptance]) -> None:
        self.values = values

    def save(self, acceptance: DecisionAcceptance) -> None:
        self.values.append(acceptance)

    def load_all(self) -> list[DecisionAcceptance]:
        return self.values

    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        return next((item for item in self.values if item.id == acceptance_id), None)


class ActionRepo(DecisionActionRepository):
    def __init__(self, values: list[DecisionAction]) -> None:
        self.values = values

    def save(self, action: DecisionAction) -> None:
        self.values.append(action)

    def load_all(self) -> list[DecisionAction]:
        return self.values

    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        return next((item for item in self.values if item.id == action_id), None)


class OutcomeRepo(DecisionOutcomeRepository):
    def __init__(self, values: list[DecisionOutcome] | None = None) -> None:
        self.values = values or []
        self.save_calls: list[DecisionOutcome] = []

    def save(self, outcome: DecisionOutcome) -> None:
        self.save_calls.append(outcome)
        self.values.append(outcome)

    def load_all(self) -> list[DecisionOutcome]:
        return self.values

    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        return next((item for item in self.values if item.id == outcome_id), None)


def make_decision(**updates: object) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Record outcomes",
        "objective": "Preserve factual validation",
        "context_summary": "Actions need explicit outcomes.",
        "alternatives": ("Outcome record", "Mutable status"),
        "proposed_option": "Outcome record",
        "rationale": "Immutable history is auditable.",
        "proposed_by": "codex",
        "idempotency_key": "decision-outcome",
    }
    values.update(updates)
    return Decision.model_validate(values)


def make_acceptance(decision_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "accepted_by": "owner",
        "reason": "Proceed.",
        "idempotency_key": "accept-outcome",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def make_action(decision_id: UUID, acceptance_id: UUID, **updates: object) -> DecisionAction:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_type": "validation",
        "summary": "Ran checks.",
        "performed_by": "codex",
        "started_at": datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        "idempotency_key": "action-outcome",
    }
    values.update(updates)
    return DecisionAction.model_validate(values)


def add_values(
    decision: Decision, acceptance: DecisionAcceptance, actions: list[DecisionAction]
) -> dict[str, object]:
    return {
        "decision_id": decision.id,
        "acceptance_id": acceptance.id,
        "action_ids": [action.id for action in actions],
        "result": DecisionOutcomeResult.SUCCEEDED,
        "summary": "All checks passed.",
        "validated_by": "pytest",
        "validated_at": datetime(2026, 7, 18, 11, 0, tzinfo=UTC),
        "idempotency_key": "outcome-1",
        "evidence_references": [EvidenceReference(kind="test", locator="pytest:all")],
        "metrics": {"passed": 681, "clean": True},
        "tags": ["validation"],
    }


def make_service(
    decisions: list[Decision],
    acceptances: list[DecisionAcceptance],
    actions: list[DecisionAction],
    outcomes: list[DecisionOutcome] | None = None,
) -> tuple[DecisionOutcomeService, OutcomeRepo]:
    outcome_repo = OutcomeRepo(outcomes)
    return (
        DecisionOutcomeService(
            outcome_repo,
            DecisionRepo(decisions),
            AcceptanceRepo(acceptances),
            ActionRepo(actions),
        ),
        outcome_repo,
    )


def valid_graph() -> tuple[Decision, DecisionAcceptance, list[DecisionAction]]:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    actions = [make_action(decision.id, acceptance.id)]
    return decision, acceptance, actions


def test_add_validates_relations_then_saves_complete_outcome() -> None:
    decision, acceptance, actions = valid_graph()
    service, repository = make_service([decision], [acceptance], actions)

    outcome = service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    assert repository.save_calls == [outcome]
    assert outcome.decision_id == decision.id
    assert outcome.action_ids == (actions[0].id,)
    assert dict(outcome.metrics) == {"passed": 681, "clean": True}
    assert service.show(outcome.id) == outcome


def test_add_rejects_missing_decision_without_write() -> None:
    decision, acceptance, actions = valid_graph()
    service, repository = make_service([], [acceptance], actions)
    with pytest.raises(DecisionOutcomeDecisionNotFoundError):
        service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_add_rejects_missing_or_mismatched_acceptance_without_write() -> None:
    decision, acceptance, actions = valid_graph()
    service, repository = make_service([decision], [], actions)
    with pytest.raises(DecisionOutcomeAcceptanceNotFoundError):
        service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]
    assert repository.save_calls == []

    other_decision = make_decision(idempotency_key="other")
    wrong = make_acceptance(other_decision.id)
    service, repository = make_service([decision, other_decision], [wrong], actions)
    values = add_values(decision, acceptance, actions)
    values["acceptance_id"] = wrong.id
    with pytest.raises(DecisionOutcomeAcceptanceMismatchError):
        service.add(**values)  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_add_rejects_duplicate_missing_or_wrong_action_relations() -> None:
    decision, acceptance, actions = valid_graph()
    values = add_values(decision, acceptance, actions)
    service, repository = make_service([decision], [acceptance], actions)
    values["action_ids"] = [actions[0].id, actions[0].id]
    with pytest.raises(DecisionOutcomeDuplicateActionError):
        service.add(**values)  # type: ignore[arg-type]

    missing_id = UUID("99999999-9999-9999-9999-999999999999")
    values["action_ids"] = [missing_id]
    with pytest.raises(DecisionOutcomeActionNotFoundError):
        service.add(**values)  # type: ignore[arg-type]

    other_decision = make_decision(idempotency_key="other")
    wrong_decision_action = make_action(other_decision.id, acceptance.id)
    service, repository = make_service(
        [decision, other_decision], [acceptance], [wrong_decision_action]
    )
    values["action_ids"] = [wrong_decision_action.id]
    with pytest.raises(DecisionOutcomeActionDecisionMismatchError):
        service.add(**values)  # type: ignore[arg-type]

    other_acceptance = make_acceptance(decision.id, idempotency_key="other-acceptance")
    wrong_acceptance_action = make_action(
        decision.id, other_acceptance.id, idempotency_key="other-action"
    )
    service, repository = make_service(
        [decision], [acceptance, other_acceptance], [wrong_acceptance_action]
    )
    values["action_ids"] = [wrong_acceptance_action.id]
    with pytest.raises(DecisionOutcomeActionAcceptanceMismatchError):
        service.add(**values)  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_add_rejects_validation_before_earliest_action_start() -> None:
    decision, acceptance, actions = valid_graph()
    service, repository = make_service([decision], [acceptance], actions)
    values = add_values(decision, acceptance, actions)
    values["validated_at"] = datetime(2026, 7, 18, 9, 59, tzinfo=UTC)

    with pytest.raises(DecisionOutcomeValidationBeforeActionError):
        service.add(**values)  # type: ignore[arg-type]
    assert repository.save_calls == []


def test_equivalent_replay_returns_existing_and_conflict_is_visible() -> None:
    decision, acceptance, actions = valid_graph()
    first_service, first_repo = make_service([decision], [acceptance], actions)
    values = add_values(decision, acceptance, actions)
    existing = first_service.add(**values)  # type: ignore[arg-type]
    replay_service, replay_repo = make_service([decision], [acceptance], actions, [existing])

    replay = replay_service.add(**values)  # type: ignore[arg-type]

    assert replay is existing
    assert replay_repo.save_calls == []
    values["summary"] = "Different result."
    with pytest.raises(DecisionOutcomeIdempotencyConflictError):
        replay_service.add(**values)  # type: ignore[arg-type]
    assert len(first_repo.save_calls) == 1


def test_evidence_capture_time_is_excluded_from_semantic_replay() -> None:
    decision, acceptance, actions = valid_graph()
    service, _ = make_service([decision], [acceptance], actions)
    values = add_values(decision, acceptance, actions)
    existing = service.add(**values)  # type: ignore[arg-type]
    values["evidence_references"] = [
        EvidenceReference(
            kind="test",
            locator="pytest:all",
            captured_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        )
    ]

    assert service.add(**values) is existing  # type: ignore[arg-type]


def test_multiple_distinct_outcomes_and_list_order_are_preserved() -> None:
    decision, acceptance, actions = valid_graph()
    second_action = make_action(decision.id, acceptance.id, idempotency_key="action-2")
    service, repository = make_service([decision], [acceptance], [*actions, second_action])
    first = service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]
    second_values = add_values(decision, acceptance, [second_action])
    second_values["idempotency_key"] = "outcome-2"
    second_values["result"] = DecisionOutcomeResult.PARTIAL
    second = service.add(**second_values)  # type: ignore[arg-type]

    assert service.list_for_decision(decision.id) == [first, second]
    assert repository.save_calls == [first, second]


def test_show_missing_and_list_missing_decision_are_explicit() -> None:
    service, _ = make_service([], [], [])
    missing = UUID("88888888-8888-8888-8888-888888888888")
    with pytest.raises(DecisionOutcomeNotFoundError):
        service.show(missing)
    with pytest.raises(DecisionOutcomeDecisionNotFoundError):
        service.list_for_decision(missing)


def test_summary_empty_and_multiple_outcomes_are_deterministic() -> None:
    decision, acceptance, actions = valid_graph()
    second_action = make_action(decision.id, acceptance.id, idempotency_key="action-2")
    service, _ = make_service([decision], [acceptance], [*actions, second_action])
    empty = service.summary_for_decision(decision.id)
    assert empty.outcome_count == 0
    assert empty.latest_result is None
    assert dict(empty.results_by_type) == {
        "succeeded": 0,
        "failed": 0,
        "partial": 0,
        "unknown": 0,
    }

    values = add_values(decision, acceptance, actions)
    first = service.add(**values)  # type: ignore[arg-type]
    values["idempotency_key"] = "outcome-2"
    values["action_ids"] = [actions[0].id, second_action.id]
    values["result"] = DecisionOutcomeResult.FAILED
    values["validated_at"] = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    latest = service.add(**values)  # type: ignore[arg-type]

    summary = service.summary_for_decision(decision.id)
    assert summary.outcome_count == 2
    assert summary.latest_result is latest.result
    assert summary.latest_validated_at == latest.validated_at
    assert summary.linked_action_count == 2
    assert summary.results_by_type["succeeded"] == 1
    assert summary.results_by_type["failed"] == 1
    assert summary.has_success is True
    assert summary.has_failure is True
    assert first != latest
    with pytest.raises(TypeError):
        summary.results_by_type["failed"] = 0  # type: ignore[index]


def test_summary_detects_corrupt_missing_action_relation() -> None:
    decision, acceptance, actions = valid_graph()
    service, _ = make_service([decision], [acceptance], actions)
    outcome = service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]
    corrupt_service, _ = make_service([decision], [acceptance], [], [outcome])

    with pytest.raises(DecisionOutcomeActionNotFoundError):
        corrupt_service.summary_for_decision(decision.id)


def test_duplicate_idempotency_key_raises_ambiguity_error() -> None:
    decision, acceptance, actions = valid_graph()
    values = add_values(decision, acceptance, actions)
    recorded = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    first = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000a1"), "recorded_at": recorded}
    )
    second = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000a2"), "recorded_at": recorded}
    )
    service, repository = make_service([decision], [acceptance], actions, [first, second])

    with pytest.raises(DecisionOutcomeIdempotencyAmbiguityError) as exc:
        service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    assert exc.value.decision_id == decision.id
    assert exc.value.idempotency_key == "outcome-1"
    assert exc.value.match_count == 2


def test_ambiguity_never_calls_save() -> None:
    decision, acceptance, actions = valid_graph()
    values = add_values(decision, acceptance, actions)
    recorded = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    first = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000b1"), "recorded_at": recorded}
    )
    second = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000b2"), "recorded_at": recorded}
    )
    service, repository = make_service([decision], [acceptance], actions, [first, second])

    with pytest.raises(DecisionOutcomeIdempotencyAmbiguityError):
        service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    assert repository.save_calls == []


def test_ambiguity_is_order_independent() -> None:
    decision, acceptance, actions = valid_graph()
    values = add_values(decision, acceptance, actions)
    recorded = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    outcome_a = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000c1"), "recorded_at": recorded}
    )
    outcome_b = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000c2"), "recorded_at": recorded}
    )

    forward_service, _ = make_service([decision], [acceptance], actions, [outcome_a, outcome_b])
    reversed_service, _ = make_service([decision], [acceptance], actions, [outcome_b, outcome_a])

    with pytest.raises(DecisionOutcomeIdempotencyAmbiguityError) as exc_forward:
        forward_service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    with pytest.raises(DecisionOutcomeIdempotencyAmbiguityError) as exc_reversed:
        reversed_service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    assert exc_reversed.value.decision_id == exc_forward.value.decision_id
    assert exc_reversed.value.idempotency_key == exc_forward.value.idempotency_key
    assert exc_reversed.value.match_count == exc_forward.value.match_count
    assert str(exc_reversed.value) == str(exc_forward.value)


def test_semantically_equivalent_duplicates_also_ambiguous() -> None:
    decision, acceptance, actions = valid_graph()
    values = add_values(decision, acceptance, actions)
    recorded = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    first = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000d1"), "recorded_at": recorded}
    )
    second = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000d2"), "recorded_at": recorded}
    )
    service, repository = make_service([decision], [acceptance], actions, [first, second])

    with pytest.raises(DecisionOutcomeIdempotencyAmbiguityError) as exc:
        service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    assert exc.value.match_count == 2
    assert repository.save_calls == []


def test_different_payload_duplicates_also_ambiguous_rather_than_conflict() -> None:
    decision, acceptance, actions = valid_graph()
    values = add_values(decision, acceptance, actions)
    recorded = datetime(2026, 7, 18, 14, 0, tzinfo=UTC)
    first = DecisionOutcome.model_validate(
        {**values, "id": UUID("00000000-0000-0000-0000-0000000000e1"), "recorded_at": recorded}
    )
    # Second outcome with same key but different semantic payload
    second = DecisionOutcome.model_validate(
        {
            **values,
            "id": UUID("00000000-0000-0000-0000-0000000000e2"),
            "recorded_at": recorded,
            "summary": "A different outcome.",
        }
    )
    service, repository = make_service([decision], [acceptance], actions, [first, second])

    with pytest.raises(DecisionOutcomeIdempotencyAmbiguityError) as exc:
        service.add(**add_values(decision, acceptance, actions))  # type: ignore[arg-type]

    assert exc.value.match_count == 2
    assert repository.save_calls == []
