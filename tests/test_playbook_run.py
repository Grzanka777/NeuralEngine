from datetime import UTC
from uuid import UUID

from neural_engine.domain import PlaybookRun


def test_playbook_run_has_domain_defaults_and_preserves_required_fields() -> None:
    playbook_id = UUID("11111111-1111-1111-1111-111111111111")

    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="A flaky test appeared in CI",
        actions_taken=["Ran the playbook manually"],
        outcome="The unstable dependency was isolated",
        success=True,
    )

    assert isinstance(run.id, UUID)
    assert run.timestamp.tzinfo == UTC
    assert run.playbook_id == playbook_id
    assert run.revision_id is None
    assert run.situation == "A flaky test appeared in CI"
    assert run.actions_taken == ["Ran the playbook manually"]
    assert run.outcome == "The unstable dependency was isolated"
    assert run.success is True
    assert run.evidence == []
    assert run.notes is None
    assert run.tags == []


def test_playbook_run_preserves_optional_fields() -> None:
    playbook_id = UUID("22222222-2222-2222-2222-222222222222")
    revision_id = UUID("33333333-3333-3333-3333-333333333333")

    run = PlaybookRun(
        playbook_id=playbook_id,
        revision_id=revision_id,
        situation="A deployment failed",
        actions_taken=["Checked logs"],
        outcome="The failed dependency was identified",
        success=False,
        evidence=["Log line 42"],
        notes="Manual follow-up needed",
        tags=["deployment", "manual"],
    )

    assert run.evidence == ["Log line 42"]
    assert run.revision_id == revision_id
    assert run.notes == "Manual follow-up needed"
    assert run.tags == ["deployment", "manual"]


def test_playbook_run_revision_relation_serializes() -> None:
    revision_id = UUID("44444444-4444-4444-4444-444444444444")
    run = PlaybookRun(
        playbook_id=UUID("55555555-5555-5555-5555-555555555555"),
        revision_id=revision_id,
        situation="Serialized provenance",
        actions_taken=["Applied revision"],
        outcome="Recorded",
        success=True,
    )

    assert PlaybookRun.model_validate_json(run.model_dump_json()).revision_id == revision_id
