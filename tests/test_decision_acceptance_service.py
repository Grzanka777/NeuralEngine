from uuid import UUID

import pytest

from neural_engine.application.decision_acceptance_service import (
    DecisionAcceptanceDecisionNotFoundError,
    DecisionAcceptanceIdempotencyConflictError,
    DecisionAcceptanceNotFoundError,
    DecisionAcceptanceService,
    DecisionAlreadyAcceptedError,
)
from neural_engine.domain import Decision, DecisionAcceptance, EvidenceReference
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)
from neural_engine.ports.decision_repository import DecisionRepository


class FakeAcceptanceRepository(DecisionAcceptanceRepository):
    def __init__(self, acceptances: list[DecisionAcceptance] | None = None) -> None:
        self.acceptances = acceptances or []
        self.save_calls: list[DecisionAcceptance] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []

    def save(self, acceptance: DecisionAcceptance) -> None:
        self.save_calls.append(acceptance)
        self.acceptances.append(acceptance)

    def load_all(self) -> list[DecisionAcceptance]:
        self.load_all_calls += 1
        return self.acceptances

    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        self.requested_ids.append(acceptance_id)
        return next(
            (acceptance for acceptance in self.acceptances if acceptance.id == acceptance_id),
            None,
        )


class FakeDecisionRepository(DecisionRepository):
    def __init__(self, decisions: list[Decision] | None = None) -> None:
        self.decisions = decisions or []
        self.requested_ids: list[UUID] = []

    def save(self, decision: Decision) -> None:
        self.decisions.append(decision)

    def load_all(self) -> list[Decision]:
        return self.decisions

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        self.requested_ids.append(decision_id)
        return next((item for item in self.decisions if item.id == decision_id), None)


def make_decision(**updates: object) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Accept the foundation",
        "objective": "Authorize a proposed implementation",
        "context_summary": "The proposal has completed architecture review.",
        "alternatives": ("Accept", "Keep proposed"),
        "proposed_option": "Accept",
        "rationale": "Review evidence supports the proposal.",
        "proposed_by": "architecture-review",
        "idempotency_key": "decision-1",
    }
    values.update(updates)
    return Decision.model_validate(values)


def make_acceptance(decision_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "accepted_by": "architecture-owner",
        "reason": "Approved after review.",
        "idempotency_key": "acceptance-1",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def make_service(
    decisions: list[Decision] | None = None,
    acceptances: list[DecisionAcceptance] | None = None,
) -> tuple[DecisionAcceptanceService, FakeAcceptanceRepository, FakeDecisionRepository]:
    acceptance_repository = FakeAcceptanceRepository(acceptances)
    decision_repository = FakeDecisionRepository(decisions)
    return (
        DecisionAcceptanceService(acceptance_repository, decision_repository),
        acceptance_repository,
        decision_repository,
    )


def test_accept_validates_decision_and_persists_only_acceptance() -> None:
    decision = make_decision()
    original_payload = decision.model_dump()
    service, acceptance_repository, decision_repository = make_service([decision])
    evidence = EvidenceReference(kind="manual_decision", locator="approval:review")

    acceptance = service.accept(
        decision.id,
        accepted_by=" architecture-owner ",
        reason=" Approved after review. ",
        idempotency_key=" acceptance-1 ",
        evidence_references=[evidence],
        tags=[" architecture "],
    )

    assert decision_repository.requested_ids == [decision.id]
    assert acceptance_repository.save_calls == [acceptance]
    assert acceptance.decision_id == decision.id
    assert acceptance.evidence_references == (evidence,)
    assert decision.model_dump() == original_payload


def test_accept_rejects_missing_decision_without_loading_or_writing() -> None:
    missing_id = UUID("11111111-1111-1111-1111-111111111111")
    service, repository, _ = make_service()

    with pytest.raises(DecisionAcceptanceDecisionNotFoundError) as error:
        service.accept(missing_id, "owner", "reason", "key")

    assert error.value.decision_id == missing_id
    assert repository.load_all_calls == 0
    assert repository.save_calls == []


def test_equivalent_replay_returns_existing_without_writing() -> None:
    decision = make_decision()
    existing = make_acceptance(
        decision.id,
        evidence_references=(EvidenceReference(kind="manual", locator="approval:1"),),
        tags=("architecture",),
    )
    service, repository, _ = make_service([decision], [existing])

    replayed = service.accept(
        decision.id,
        "architecture-owner",
        "Approved after review.",
        "acceptance-1",
        evidence_references=[EvidenceReference(kind="manual", locator="approval:1")],
        tags=["architecture"],
    )

    assert replayed is existing
    assert repository.save_calls == []


def test_same_key_with_different_payload_raises_without_writing() -> None:
    decision = make_decision()
    existing = make_acceptance(decision.id)
    service, repository, _ = make_service([decision], [existing])

    with pytest.raises(DecisionAcceptanceIdempotencyConflictError) as error:
        service.accept(decision.id, "other-owner", "Approved after review.", "acceptance-1")

    assert error.value.decision_id == decision.id
    assert error.value.idempotency_key == "acceptance-1"
    assert repository.save_calls == []


def test_second_acceptance_with_another_key_raises_without_writing() -> None:
    decision = make_decision()
    existing = make_acceptance(decision.id)
    service, repository, _ = make_service([decision], [existing])

    with pytest.raises(DecisionAlreadyAcceptedError) as error:
        service.accept(decision.id, "owner", "Another approval", "acceptance-2")

    assert error.value.decision_id == decision.id
    assert error.value.acceptance_id == existing.id
    assert repository.save_calls == []


def test_list_for_decision_validates_filters_and_preserves_order() -> None:
    decision = make_decision()
    other_decision = make_decision(idempotency_key="decision-2")
    first = make_acceptance(decision.id, idempotency_key="first")
    unrelated = make_acceptance(other_decision.id, idempotency_key="other")
    second = make_acceptance(decision.id, idempotency_key="second")
    service, repository, _ = make_service(
        [decision, other_decision],
        [second, unrelated, first],
    )

    assert service.list_for_decision(decision.id) == [second, first]
    assert repository.load_all_calls == 1


def test_list_for_decision_rejects_missing_decision_without_loading() -> None:
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    service, repository, _ = make_service()

    with pytest.raises(DecisionAcceptanceDecisionNotFoundError):
        service.list_for_decision(missing_id)

    assert repository.load_all_calls == 0


def test_show_returns_existing_and_rejects_missing() -> None:
    decision = make_decision()
    acceptance = make_acceptance(decision.id)
    service, repository, _ = make_service([decision], [acceptance])

    assert service.show(acceptance.id) == acceptance

    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    with pytest.raises(DecisionAcceptanceNotFoundError) as error:
        service.show(missing_id)

    assert error.value.acceptance_id == missing_id
    assert repository.requested_ids == [acceptance.id, missing_id]
