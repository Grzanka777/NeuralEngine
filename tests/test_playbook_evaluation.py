from datetime import UTC
from uuid import UUID

from neural_engine.domain import PlaybookEffectiveness, PlaybookEvaluation


def test_playbook_evaluation_has_domain_defaults_and_preserves_required_fields() -> None:
    run_id = UUID("11111111-1111-1111-1111-111111111111")

    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["The playbook isolated the issue"],
    )

    assert isinstance(evaluation.id, UUID)
    assert evaluation.timestamp.tzinfo == UTC
    assert evaluation.run_id == run_id
    assert evaluation.effectiveness == PlaybookEffectiveness.EFFECTIVE
    assert evaluation.findings == ["The playbook isolated the issue"]
    assert evaluation.improvements == []
    assert evaluation.evidence == []
    assert evaluation.notes is None
    assert evaluation.tags == []


def test_playbook_evaluation_preserves_optional_fields() -> None:
    run_id = UUID("22222222-2222-2222-2222-222222222222")

    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.PARTIAL,
        findings=["The first step helped"],
        improvements=["Clarify rollback criteria"],
        evidence=["Incident log"],
        notes="External reviewer supplied this evaluation",
        tags=["ops", "review"],
    )

    assert evaluation.improvements == ["Clarify rollback criteria"]
    assert evaluation.evidence == ["Incident log"]
    assert evaluation.notes == "External reviewer supplied this evaluation"
    assert evaluation.tags == ["ops", "review"]


def test_playbook_evaluation_accepts_all_effectiveness_values() -> None:
    run_id = UUID("33333333-3333-3333-3333-333333333333")

    for effectiveness in PlaybookEffectiveness:
        evaluation = PlaybookEvaluation(
            run_id=run_id,
            effectiveness=effectiveness,
            findings=["Finding recorded"],
        )

        assert evaluation.effectiveness == effectiveness
