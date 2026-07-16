from datetime import UTC
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import PlaybookRevisionApplication


def make_application(
    reason: str = "Record explicit application boundary",
    applied_by: str | None = None,
    notes: str | None = None,
    tags: tuple[str, ...] = (),
    source_activation_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> PlaybookRevisionApplication:
    return PlaybookRevisionApplication(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        revision_id=UUID("22222222-2222-2222-2222-222222222222"),
        proposal_id=UUID("33333333-3333-3333-3333-333333333333"),
        reason=reason,
        applied_by=applied_by,
        notes=notes,
        tags=tags,
        source_activation_id=source_activation_id,
        idempotency_key=idempotency_key,
    )


def test_playbook_revision_application_has_defaults_and_required_fields() -> None:
    playbook_id = UUID("11111111-1111-1111-1111-111111111111")
    revision_id = UUID("22222222-2222-2222-2222-222222222222")
    proposal_id = UUID("33333333-3333-3333-3333-333333333333")

    application = PlaybookRevisionApplication(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        reason="Manual application record",
    )

    assert isinstance(application.id, UUID)
    assert application.applied_at.tzinfo == UTC
    assert application.playbook_id == playbook_id
    assert application.revision_id == revision_id
    assert application.proposal_id == proposal_id
    assert application.reason == "Manual application record"
    assert application.applied_by is None
    assert application.notes is None
    assert application.tags == ()
    assert application.source_activation_id is None
    assert application.idempotency_key is None
    assert application.content_changed is False


def test_playbook_revision_application_preserves_custom_metadata() -> None:
    source_activation_id = UUID("44444444-4444-4444-4444-444444444444")

    application = make_application(
        applied_by="external-system",
        notes="Application intent recorded for audit",
        tags=("manual", "audit"),
        source_activation_id=source_activation_id,
        idempotency_key="apply-1",
    )

    assert application.applied_by == "external-system"
    assert application.notes == "Application intent recorded for audit"
    assert application.tags == ("manual", "audit")
    assert application.source_activation_id == source_activation_id
    assert application.idempotency_key == "apply-1"


def test_playbook_revision_application_preserves_supplied_text_without_normalization() -> None:
    application = make_application(
        reason="  Manual reason  ",
        applied_by="  reviewer  ",
        notes="  note  ",
        tags=("  manual  ",),
        idempotency_key="  key  ",
    )

    assert application.reason == "  Manual reason  "
    assert application.applied_by == "  reviewer  "
    assert application.notes == "  note  "
    assert application.tags == ("  manual  ",)
    assert application.idempotency_key == "  key  "


def test_playbook_revision_application_rejects_blank_reason() -> None:
    with pytest.raises(ValidationError):
        make_application(reason="   ")


def test_playbook_revision_application_rejects_blank_applied_by() -> None:
    with pytest.raises(ValidationError):
        make_application(applied_by="   ")


def test_playbook_revision_application_rejects_blank_notes() -> None:
    with pytest.raises(ValidationError):
        make_application(notes="   ")


def test_playbook_revision_application_rejects_blank_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        make_application(idempotency_key="   ")


def test_playbook_revision_application_rejects_blank_tag() -> None:
    with pytest.raises(ValidationError):
        make_application(tags=("manual", "   "))


def test_playbook_revision_application_tags_are_immutable_tuple() -> None:
    application = make_application(tags=("manual", "application"))

    assert application.tags == ("manual", "application")
    assert isinstance(application.tags, tuple)

    with pytest.raises((TypeError, ValueError)):
        application.tags = ("mutated",)


def test_playbook_revision_application_json_round_trip_preserves_all_data() -> None:
    application = make_application(
        applied_by="reviewer",
        notes="Round-trip notes",
        tags=("round", "trip"),
        source_activation_id=UUID("55555555-5555-5555-5555-555555555555"),
        idempotency_key="round-trip",
    )

    restored = PlaybookRevisionApplication.model_validate_json(application.model_dump_json())

    assert restored == application
    assert restored.model_dump() == application.model_dump()


def test_playbook_revision_application_does_not_validate_cross_aggregate_existence() -> None:
    application = PlaybookRevisionApplication(
        playbook_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        revision_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        proposal_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        reason="Only local invariants are validated",
    )

    assert application.playbook_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert application.revision_id == UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert application.proposal_id == UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
