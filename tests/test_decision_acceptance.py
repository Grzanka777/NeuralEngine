from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import DecisionAcceptance, EvidenceReference


def make_acceptance(**updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": UUID("11111111-1111-1111-1111-111111111111"),
        "accepted_by": "architecture-owner",
        "reason": "The proposed boundary is approved.",
        "idempotency_key": "acceptance-1",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def test_acceptance_constructs_with_normalized_immutable_values() -> None:
    evidence = EvidenceReference(kind=" manual_decision ", locator=" approval:review ")

    acceptance = make_acceptance(
        accepted_by=" architecture-owner ",
        reason=" Approved after review. ",
        idempotency_key=" acceptance-1 ",
        evidence_references=(evidence,),
        tags=(" architecture ", "Architecture", " lifecycle "),
    )

    assert acceptance.accepted_by == "architecture-owner"
    assert acceptance.reason == "Approved after review."
    assert acceptance.idempotency_key == "acceptance-1"
    assert acceptance.evidence_references[0].kind == "manual_decision"
    assert acceptance.tags == ("architecture", "lifecycle")
    assert acceptance.accepted_at.tzinfo == UTC
    assert not hasattr(acceptance, "status")

    with pytest.raises(ValidationError):
        acceptance.reason = "Changed"


@pytest.mark.parametrize("field", ["accepted_by", "reason", "idempotency_key"])
def test_acceptance_rejects_blank_required_text(field: str) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        make_acceptance(**{field: "  "})


def test_acceptance_rejects_invalid_decision_id() -> None:
    with pytest.raises(ValidationError):
        make_acceptance(decision_id="not-a-uuid")


def test_acceptance_requires_aware_timestamp_and_normalizes_to_utc() -> None:
    with pytest.raises(ValidationError, match="accepted_at must be timezone-aware"):
        make_acceptance(accepted_at=datetime(2026, 7, 17, 10, 0))

    acceptance = make_acceptance(
        accepted_at=datetime(2026, 7, 17, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    )
    assert acceptance.accepted_at == datetime(2026, 7, 17, 10, 0, tzinfo=UTC)


def test_acceptance_rejects_blank_tag_and_normalizes_unique_tags() -> None:
    with pytest.raises(ValidationError, match="must not contain blank"):
        make_acceptance(tags=("valid", " "))

    acceptance = make_acceptance(tags=(" review ", "Review", " decision "))
    assert acceptance.tags == ("review", "decision")


def test_acceptance_json_round_trip_preserves_embedded_evidence() -> None:
    acceptance = make_acceptance(
        evidence_references=(
            EvidenceReference(
                kind="manual_decision",
                locator="approval:architecture-review",
                repository_or_project="NeuralEngine",
                summary="Explicit approval",
            ),
        ),
        tags=("architecture",),
    )

    restored = DecisionAcceptance.model_validate_json(acceptance.model_dump_json())

    assert restored == acceptance
    assert restored.evidence_references[0] == acceptance.evidence_references[0]
