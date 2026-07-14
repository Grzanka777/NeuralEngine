from datetime import UTC
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import (
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
)


def make_activation(
    decision: PlaybookRevisionActivationDecision = PlaybookRevisionActivationDecision.ACTIVE,
    previous_revision_id: UUID | None = None,
    reason: str = "Manual reviewer selected this revision",
    decided_by: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> PlaybookRevisionActivation:
    return PlaybookRevisionActivation(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        revision_id=UUID("22222222-2222-2222-2222-222222222222"),
        proposal_id=UUID("33333333-3333-3333-3333-333333333333"),
        decision=decision,
        reason=reason,
        previous_revision_id=previous_revision_id,
        decided_by=decided_by,
        notes=notes,
        tags=tags or [],
    )


def test_playbook_revision_activation_has_domain_defaults_and_required_fields() -> None:
    playbook_id = UUID("11111111-1111-1111-1111-111111111111")
    revision_id = UUID("22222222-2222-2222-2222-222222222222")
    proposal_id = UUID("33333333-3333-3333-3333-333333333333")

    activation = PlaybookRevisionActivation(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        reason="Manual review selected this revision",
    )

    assert isinstance(activation.id, UUID)
    assert activation.timestamp.tzinfo == UTC
    assert activation.playbook_id == playbook_id
    assert activation.revision_id == revision_id
    assert activation.proposal_id == proposal_id
    assert activation.decision == PlaybookRevisionActivationDecision.ACTIVE
    assert activation.reason == "Manual review selected this revision"
    assert activation.previous_revision_id is None
    assert activation.decided_by is None
    assert activation.notes is None
    assert activation.tags == []


def test_playbook_revision_activation_preserves_optional_fields() -> None:
    previous_revision_id = UUID("44444444-4444-4444-4444-444444444444")

    activation = make_activation(
        previous_revision_id=previous_revision_id,
        decided_by="external-review",
        notes="Selected after manual comparison",
        tags=["manual", "selected"],
    )

    assert activation.previous_revision_id == previous_revision_id
    assert activation.decided_by == "external-review"
    assert activation.notes == "Selected after manual comparison"
    assert activation.tags == ["manual", "selected"]


def test_playbook_revision_activation_preserves_supplied_text_without_normalization() -> None:
    activation = make_activation(
        reason="  Manual reason  ",
        decided_by="  reviewer  ",
        notes="  note  ",
        tags=["  manual  "],
    )

    assert activation.reason == "  Manual reason  "
    assert activation.decided_by == "  reviewer  "
    assert activation.notes == "  note  "
    assert activation.tags == ["  manual  "]


def test_playbook_revision_activation_rejects_blank_reason() -> None:
    with pytest.raises(ValidationError):
        make_activation(reason="   ")


def test_playbook_revision_activation_rejects_blank_decided_by() -> None:
    with pytest.raises(ValidationError):
        make_activation(decided_by="   ")


def test_playbook_revision_activation_rejects_blank_notes() -> None:
    with pytest.raises(ValidationError):
        make_activation(notes="   ")


def test_playbook_revision_activation_rejects_blank_tag() -> None:
    with pytest.raises(ValidationError):
        make_activation(tags=["manual", "   "])


def test_playbook_revision_activation_allows_active_without_previous_revision() -> None:
    activation = make_activation(
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        previous_revision_id=None,
    )

    assert activation.decision == PlaybookRevisionActivationDecision.ACTIVE
    assert activation.previous_revision_id is None


def test_playbook_revision_activation_allows_active_with_previous_revision() -> None:
    previous_revision_id = UUID("55555555-5555-5555-5555-555555555555")

    activation = make_activation(
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        previous_revision_id=previous_revision_id,
    )

    assert activation.decision == PlaybookRevisionActivationDecision.ACTIVE
    assert activation.previous_revision_id == previous_revision_id


def test_playbook_revision_activation_requires_previous_revision_for_superseded() -> None:
    with pytest.raises(ValidationError):
        make_activation(decision=PlaybookRevisionActivationDecision.SUPERSEDED)


def test_playbook_revision_activation_allows_superseded_with_previous_revision() -> None:
    previous_revision_id = UUID("66666666-6666-6666-6666-666666666666")

    activation = make_activation(
        decision=PlaybookRevisionActivationDecision.SUPERSEDED,
        previous_revision_id=previous_revision_id,
    )

    assert activation.decision == PlaybookRevisionActivationDecision.SUPERSEDED
    assert activation.previous_revision_id == previous_revision_id


def test_playbook_revision_activation_rejects_previous_revision_for_rejected() -> None:
    with pytest.raises(ValidationError):
        make_activation(
            decision=PlaybookRevisionActivationDecision.REJECTED,
            previous_revision_id=UUID("77777777-7777-7777-7777-777777777777"),
        )


def test_playbook_revision_activation_is_immutable() -> None:
    activation = make_activation()

    with pytest.raises((TypeError, ValueError)):
        activation.reason = "Mutated"


def test_playbook_revision_activation_decision_values_serialize_consistently() -> None:
    activation = make_activation(decision=PlaybookRevisionActivationDecision.REJECTED)

    assert PlaybookRevisionActivationDecision.ACTIVE.value == "active"
    assert PlaybookRevisionActivationDecision.SUPERSEDED.value == "superseded"
    assert PlaybookRevisionActivationDecision.REJECTED.value == "rejected"
    assert '"decision":"rejected"' in activation.model_dump_json()


def test_playbook_revision_activation_json_round_trip_preserves_all_data() -> None:
    activation = make_activation(
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        previous_revision_id=UUID("88888888-8888-8888-8888-888888888888"),
        decided_by="manual-reviewer",
        notes="Round-trip notes",
        tags=["round", "trip"],
    )

    restored = PlaybookRevisionActivation.model_validate_json(activation.model_dump_json())

    assert restored == activation
    assert restored.model_dump() == activation.model_dump()


def test_playbook_revision_activation_does_not_validate_cross_aggregate_existence() -> None:
    activation = PlaybookRevisionActivation(
        playbook_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        revision_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        proposal_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        reason="Only local invariants are validated",
    )

    assert activation.playbook_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert activation.revision_id == UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert activation.proposal_id == UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
