from datetime import UTC
from uuid import UUID

from neural_engine.domain import Playbook


def test_playbook_has_domain_defaults_and_preserves_fields() -> None:
    knowledge_id = UUID("11111111-1111-1111-1111-111111111111")

    playbook = Playbook(
        title="Debug flaky tests",
        situation="A test fails intermittently",
        objective="Identify the unstable dependency",
        steps=["Run the failing test repeatedly"],
        success_criteria=["The failure source is isolated"],
        knowledge_ids=[knowledge_id],
    )

    assert isinstance(playbook.id, UUID)
    assert playbook.timestamp.tzinfo == UTC
    assert playbook.title == "Debug flaky tests"
    assert playbook.situation == "A test fails intermittently"
    assert playbook.objective == "Identify the unstable dependency"
    assert playbook.steps == ["Run the failing test repeatedly"]
    assert playbook.success_criteria == ["The failure source is isolated"]
    assert playbook.constraints == []
    assert playbook.knowledge_ids == [knowledge_id]
    assert playbook.tags == []
