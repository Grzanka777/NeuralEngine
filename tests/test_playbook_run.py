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
    assert run.situation == "A flaky test appeared in CI"
    assert run.actions_taken == ["Ran the playbook manually"]
    assert run.outcome == "The unstable dependency was isolated"
    assert run.success is True
    assert run.evidence == []
    assert run.notes is None
    assert run.tags == []


def test_playbook_run_preserves_optional_fields() -> None:
    playbook_id = UUID("22222222-2222-2222-2222-222222222222")

    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="A deployment failed",
        actions_taken=["Checked logs"],
        outcome="The failed dependency was identified",
        success=False,
        evidence=["Log line 42"],
        notes="Manual follow-up needed",
        tags=["deployment", "manual"],
    )

    assert run.evidence == ["Log line 42"]
    assert run.notes == "Manual follow-up needed"
    assert run.tags == ["deployment", "manual"]
