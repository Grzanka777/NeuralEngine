from datetime import UTC
from uuid import UUID

import pytest

from neural_engine.domain import PlaybookRevision


def test_playbook_revision_has_domain_defaults_and_preserves_required_fields() -> None:
    playbook_id = UUID("11111111-1111-1111-1111-111111111111")
    proposal_id = UUID("22222222-2222-2222-2222-222222222222")
    knowledge_id = UUID("33333333-3333-3333-3333-333333333333")

    revision = PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=proposal_id,
        title="Revised flaky test playbook",
        situation="A test fails intermittently",
        objective="Identify instability faster",
        steps=["Run focused tests", "Inspect timing assumptions"],
        success_criteria=["Unstable dependency is identified"],
        knowledge_ids=[knowledge_id],
    )

    assert isinstance(revision.id, UUID)
    assert revision.timestamp.tzinfo == UTC
    assert revision.playbook_id == playbook_id
    assert revision.proposal_id == proposal_id
    assert revision.title == "Revised flaky test playbook"
    assert revision.situation == "A test fails intermittently"
    assert revision.objective == "Identify instability faster"
    assert revision.steps == ["Run focused tests", "Inspect timing assumptions"]
    assert revision.success_criteria == ["Unstable dependency is identified"]
    assert revision.knowledge_ids == [knowledge_id]
    assert revision.notes is None
    assert revision.tags == []


def test_playbook_revision_preserves_optional_notes_and_tags() -> None:
    revision = PlaybookRevision(
        playbook_id=UUID("44444444-4444-4444-4444-444444444444"),
        proposal_id=UUID("55555555-5555-5555-5555-555555555555"),
        title="Revision with metadata",
        situation="Manual review found ambiguity",
        objective="Clarify manual use",
        steps=["Apply explicit verification"],
        success_criteria=["Verification is explicit"],
        knowledge_ids=[UUID("66666666-6666-6666-6666-666666666666")],
        notes="Supplied by external reviewer",
        tags=["manual", "candidate"],
    )

    assert revision.notes == "Supplied by external reviewer"
    assert revision.tags == ["manual", "candidate"]


def test_playbook_revision_is_immutable() -> None:
    revision = PlaybookRevision(
        playbook_id=UUID("77777777-7777-7777-7777-777777777777"),
        proposal_id=UUID("88888888-8888-8888-8888-888888888888"),
        title="Immutable revision",
        situation="Immutable situation",
        objective="Immutable objective",
        steps=["Step"],
        success_criteria=["Criterion"],
        knowledge_ids=[UUID("99999999-9999-9999-9999-999999999999")],
    )

    with pytest.raises((TypeError, ValueError)):
        revision.title = "Mutated"


def test_playbook_revision_json_round_trip_preserves_all_data() -> None:
    playbook_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    proposal_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    knowledge_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    revision = PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=proposal_id,
        title="Round-trip revision",
        situation="Round-trip situation",
        objective="Round-trip objective",
        steps=["Round-trip step"],
        success_criteria=["Round-trip criterion"],
        knowledge_ids=[knowledge_id],
        notes="Round-trip notes",
        tags=["round", "trip"],
    )

    restored = PlaybookRevision.model_validate_json(revision.model_dump_json())

    assert restored == revision
    assert restored.model_dump() == revision.model_dump()
