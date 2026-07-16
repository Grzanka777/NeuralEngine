from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import Decision, EvidenceReference


def make_decision(**updates: object) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Canonical lifecycle ownership",
        "objective": "Keep active revision derivation in one service",
        "context_summary": "An application service duplicated lifecycle replay.",
        "alternatives": ("Delegate to activation service", "Keep local replay"),
        "proposed_option": "Delegate to activation service",
        "rationale": "One canonical owner prevents semantic drift.",
        "proposed_by": "architecture-review",
        "idempotency_key": "decision-active-revision-owner",
    }
    values.update(updates)
    return Decision.model_validate(values)


def test_decision_constructs_with_normalized_immutable_values() -> None:
    observation_id = UUID("11111111-1111-1111-1111-111111111111")
    evidence = EvidenceReference(
        kind=" agent_review ",
        locator=" .agent-work/reviews/review.md ",
        repository_or_project=" NeuralEngine ",
    )

    decision = make_decision(
        project_key=" NeuralEngine ",
        alternatives=(" Delegate to activation service ", " Keep local replay "),
        proposed_option=" Delegate to activation service ",
        observation_ids=(observation_id,),
        evidence_references=(evidence,),
        tags=(" architecture ", "Architecture", " lifecycle "),
    )

    assert decision.project_key == "NeuralEngine"
    assert decision.alternatives == ("Delegate to activation service", "Keep local replay")
    assert decision.proposed_option == "Delegate to activation service"
    assert decision.observation_ids == (observation_id,)
    assert decision.evidence_references[0].kind == "agent_review"
    assert decision.evidence_references[0].locator == ".agent-work/reviews/review.md"
    assert decision.tags == ("architecture", "lifecycle")
    assert decision.created_at.tzinfo == UTC
    assert not hasattr(decision, "status")


def test_decision_and_evidence_reference_are_immutable() -> None:
    evidence = EvidenceReference(kind="manual_decision", locator="decision:1")
    decision = make_decision(evidence_references=(evidence,))

    with pytest.raises(ValidationError):
        decision.title = "Changed"

    with pytest.raises(ValidationError):
        evidence.kind = "changed"


@pytest.mark.parametrize(
    "field",
    [
        "project_key",
        "title",
        "objective",
        "context_summary",
        "proposed_option",
        "rationale",
        "proposed_by",
        "idempotency_key",
    ],
)
def test_decision_rejects_blank_required_text(field: str) -> None:
    with pytest.raises(ValidationError):
        make_decision(**{field: "   "})


def test_decision_rejects_fewer_than_two_alternatives() -> None:
    with pytest.raises(ValidationError, match="at least two alternatives"):
        make_decision(alternatives=("Only option",), proposed_option="Only option")


def test_decision_rejects_blank_alternative() -> None:
    with pytest.raises(ValidationError, match="blank values"):
        make_decision(alternatives=("Valid", "  "), proposed_option="Valid")


def test_decision_rejects_duplicate_alternatives_after_normalization() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        make_decision(
            alternatives=(" Delegate ", "delegate"),
            proposed_option="Delegate",
        )


def test_decision_rejects_proposed_option_not_in_normalized_alternatives() -> None:
    with pytest.raises(ValidationError, match="exactly match"):
        make_decision(proposed_option="Create another service")


def test_decision_rejects_duplicate_observation_ids() -> None:
    observation_id = UUID("22222222-2222-2222-2222-222222222222")

    with pytest.raises(ValidationError, match="must be unique"):
        make_decision(observation_ids=(observation_id, observation_id))


def test_decision_rejects_invalid_observation_and_supersedes_ids() -> None:
    with pytest.raises(ValidationError):
        make_decision(observation_ids=("not-a-uuid",))

    with pytest.raises(ValidationError):
        make_decision(supersedes_decision_id="not-a-uuid")


def test_decision_rejects_self_supersession() -> None:
    decision_id = UUID("33333333-3333-3333-3333-333333333333")

    with pytest.raises(ValidationError, match="must not supersede itself"):
        make_decision(id=decision_id, supersedes_decision_id=decision_id)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"kind": " ", "locator": "review:1"}, "kind must not be blank"),
        ({"kind": "agent_review", "locator": " "}, "locator must not be blank"),
        ({"kind": "x" * 65, "locator": "review:1"}, "kind is too long"),
        ({"kind": "agent_review", "locator": "x" * 2049}, "locator is too long"),
    ],
)
def test_evidence_reference_rejects_invalid_bounded_fields(
    values: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        EvidenceReference.model_validate(values)


def test_evidence_reference_rejects_blank_optional_text() -> None:
    with pytest.raises(ValidationError, match="must not be blank when supplied"):
        EvidenceReference(kind="agent_review", locator="review:1", summary=" ")


def test_decision_rejects_blank_tag_and_normalizes_unique_tags() -> None:
    with pytest.raises(ValidationError, match="must not contain blank"):
        make_decision(tags=("valid", " "))

    decision = make_decision(tags=(" architecture ", "Architecture", " review "))
    assert decision.tags == ("architecture", "review")


def test_decision_json_round_trip_preserves_serialization_values() -> None:
    decision = make_decision(
        observation_ids=(UUID("44444444-4444-4444-4444-444444444444"),),
        evidence_references=(
            EvidenceReference(
                kind="git_commit",
                locator="8829fd8",
                repository_or_project="NeuralEngine",
                content_hash="sha256:abc",
                source="git",
                summary="Decision design checkpoint",
            ),
        ),
        supersedes_decision_id=UUID("55555555-5555-5555-5555-555555555555"),
        tags=("architecture", "decision"),
    )

    restored = Decision.model_validate_json(decision.model_dump_json())

    assert restored == decision
    assert restored.created_at.tzinfo is not None
    assert restored.evidence_references[0].captured_at.tzinfo is not None


def test_decision_and_evidence_reject_naive_timestamps() -> None:
    naive = datetime(2026, 7, 16, 12, 0)

    with pytest.raises(ValidationError, match="created_at must be timezone-aware"):
        make_decision(created_at=naive)

    with pytest.raises(ValidationError, match="captured_at must be timezone-aware"):
        EvidenceReference(kind="manual_decision", locator="decision:1", captured_at=naive)
