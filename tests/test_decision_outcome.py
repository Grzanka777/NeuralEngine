from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import (
    DecisionOutcome,
    DecisionOutcomeResult,
    EvidenceReference,
)


def outcome_values() -> dict[str, object]:
    return {
        "decision_id": UUID("11111111-1111-1111-1111-111111111111"),
        "acceptance_id": UUID("22222222-2222-2222-2222-222222222222"),
        "action_ids": [
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
        ],
        "result": "succeeded",
        "summary": "  All validation passed.  ",
        "validated_by": "  pytest  ",
        "validated_at": datetime(2026, 7, 18, 12, 0, tzinfo=timezone(timedelta(hours=2))),
        "evidence_references": [EvidenceReference(kind="test", locator="pytest:decision-outcome")],
        "metrics": {" passed ": 42, "coverage": 99.5, "clean": True, "suite": "full"},
        "idempotency_key": "  outcome-1  ",
        "tags": [" Validation ", "validation", "Decision"],
    }


def test_constructs_normalized_immutable_outcome() -> None:
    outcome = DecisionOutcome.model_validate(outcome_values())

    assert outcome.result is DecisionOutcomeResult.SUCCEEDED
    assert outcome.summary == "All validation passed."
    assert outcome.validated_by == "pytest"
    assert outcome.validated_at == datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    assert outcome.action_ids == (
        UUID("33333333-3333-3333-3333-333333333333"),
        UUID("44444444-4444-4444-4444-444444444444"),
    )
    assert dict(outcome.metrics) == {
        "passed": 42,
        "coverage": 99.5,
        "clean": True,
        "suite": "full",
    }
    assert outcome.tags == ("Validation", "Decision")
    assert not hasattr(outcome, "status")
    with pytest.raises(ValidationError):
        outcome.summary = "changed"
    with pytest.raises(TypeError):
        outcome.metrics["new"] = 1  # type: ignore[index]


@pytest.mark.parametrize("field", ["summary", "validated_by", "idempotency_key"])
def test_rejects_blank_required_text(field: str) -> None:
    values = outcome_values()
    values[field] = "  "
    with pytest.raises(ValidationError):
        DecisionOutcome.model_validate(values)


def test_rejects_missing_or_duplicate_actions() -> None:
    values = outcome_values()
    values["action_ids"] = []
    with pytest.raises(ValidationError):
        DecisionOutcome.model_validate(values)

    duplicate = UUID("33333333-3333-3333-3333-333333333333")
    values["action_ids"] = [duplicate, duplicate]
    with pytest.raises(ValidationError):
        DecisionOutcome.model_validate(values)


@pytest.mark.parametrize("field", ["recorded_at", "validated_at"])
def test_rejects_naive_timestamps(field: str) -> None:
    values = outcome_values()
    values[field] = datetime(2026, 7, 18, 10, 0)
    with pytest.raises(ValidationError):
        DecisionOutcome.model_validate(values)


@pytest.mark.parametrize(
    "metrics",
    [
        {" ": 1},
        {"Key": 1, "key": 2},
        {"nested": {"value": 1}},
        {"infinite": float("inf")},
        {"long": "x" * 1001},
    ],
)
def test_rejects_invalid_metrics(metrics: object) -> None:
    values = outcome_values()
    values["metrics"] = metrics
    with pytest.raises(ValidationError):
        DecisionOutcome.model_validate(values)


def test_evidence_and_metrics_round_trip() -> None:
    outcome = DecisionOutcome.model_validate(outcome_values())
    restored = DecisionOutcome.model_validate_json(outcome.model_dump_json())

    assert restored == outcome
    assert dict(restored.metrics) == dict(outcome.metrics)


def test_inconclusive_remains_invalid_as_decision_outcome_result() -> None:
    values = outcome_values()
    values["result"] = "inconclusive"
    with pytest.raises(ValidationError):
        DecisionOutcome.model_validate(values)
