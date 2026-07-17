from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import DecisionAction, EvidenceReference

DECISION_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCEPTANCE_ID = UUID("22222222-2222-2222-2222-222222222222")
STARTED_AT = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)


def make_action(**updates: object) -> DecisionAction:
    values: dict[str, object] = {
        "decision_id": DECISION_ID,
        "acceptance_id": ACCEPTANCE_ID,
        "action_type": "implementation",
        "summary": "Implemented the bounded action foundation.",
        "performed_by": "codex",
        "started_at": STARTED_AT,
        "idempotency_key": "action-1",
    }
    values.update(updates)
    return DecisionAction.model_validate(values)


def test_action_constructs_with_normalized_immutable_values() -> None:
    evidence = EvidenceReference(kind=" agent_review ", locator=" review:action ")
    action = make_action(
        action_type=" implementation ",
        summary=" Implemented the slice. ",
        performed_by=" codex ",
        idempotency_key=" action-1 ",
        evidence_references=(evidence,),
        playbook_run_id=UUID("33333333-3333-3333-3333-333333333333"),
        tags=(" architecture ", "Architecture", " action "),
    )

    assert action.action_type == "implementation"
    assert action.summary == "Implemented the slice."
    assert action.performed_by == "codex"
    assert action.evidence_references == (evidence,)
    assert action.tags == ("architecture", "action")
    assert action.recorded_at.tzinfo == UTC
    assert not hasattr(action, "status")

    with pytest.raises(ValidationError):
        action.summary = "Changed"


@pytest.mark.parametrize(
    "field",
    ["action_type", "summary", "performed_by", "idempotency_key"],
)
def test_action_rejects_blank_required_text(field: str) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        make_action(**{field: "  "})


def test_action_type_is_bounded() -> None:
    with pytest.raises(ValidationError, match="action_type is too long"):
        make_action(action_type="x" * 65)


def test_action_normalizes_aware_timestamps_to_utc() -> None:
    offset = timezone(timedelta(hours=2))
    action = make_action(
        recorded_at=datetime(2026, 7, 17, 12, 0, tzinfo=offset),
        started_at=datetime(2026, 7, 17, 11, 0, tzinfo=offset),
        completed_at=datetime(2026, 7, 17, 12, 30, tzinfo=offset),
    )

    assert action.recorded_at == datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    assert action.started_at == datetime(2026, 7, 17, 9, 0, tzinfo=UTC)
    assert action.completed_at == datetime(2026, 7, 17, 10, 30, tzinfo=UTC)


@pytest.mark.parametrize("field", ["recorded_at", "started_at", "completed_at"])
def test_action_rejects_naive_timestamps(field: str) -> None:
    with pytest.raises(ValidationError, match="timestamps must be timezone-aware"):
        make_action(**{field: datetime(2026, 7, 17, 10, 0)})


def test_action_rejects_completed_before_started() -> None:
    with pytest.raises(ValidationError, match="must not precede started_at"):
        make_action(completed_at=datetime(2026, 7, 17, 9, 59, tzinfo=UTC))


def test_action_rejects_blank_tags_and_normalizes_duplicates() -> None:
    with pytest.raises(ValidationError, match="must not contain blank"):
        make_action(tags=("valid", " "))

    assert make_action(tags=(" review ", "Review", " action ")).tags == (
        "review",
        "action",
    )


def test_action_round_trip_preserves_evidence_and_optional_playbook_run() -> None:
    action = make_action(
        completed_at=datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        evidence_references=(EvidenceReference(kind="validation", locator="run:626"),),
        playbook_run_id=UUID("44444444-4444-4444-4444-444444444444"),
        tags=("implementation",),
    )

    assert DecisionAction.model_validate_json(action.model_dump_json()) == action


def test_action_rejects_invalid_relation_uuids() -> None:
    with pytest.raises(ValidationError):
        make_action(decision_id="invalid")
    with pytest.raises(ValidationError):
        make_action(acceptance_id="invalid")
    with pytest.raises(ValidationError):
        make_action(playbook_run_id="invalid")
