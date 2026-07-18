import builtins
from datetime import UTC, datetime
from uuid import UUID

import pytest
from rich.console import Console
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.application.decision_review_service import (
    DecisionReviewDecisionNotFoundError,
    DecisionReviewIdempotencyConflictError,
    DecisionReviewNotFoundError,
    DecisionReviewOutcomeNotFoundError,
)
from neural_engine.domain import (
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    EvidenceReference,
)


class FakeDecisionReviewService:
    def __init__(self, reviews: list[DecisionReview] | None = None) -> None:
        self.reviews = reviews or []
        self.add_calls: list[dict[str, object]] = []
        self.list_calls: list[UUID] = []
        self.show_calls: list[UUID] = []
        self.missing_decision_id: UUID | None = None
        self.missing_outcome_id: UUID | None = None
        self.conflict: tuple[UUID, str] | None = None

    def add(self, **values: object) -> DecisionReview:
        self.add_calls.append(values)
        if self.missing_decision_id is not None:
            raise DecisionReviewDecisionNotFoundError(self.missing_decision_id)
        if self.missing_outcome_id is not None:
            raise DecisionReviewOutcomeNotFoundError(self.missing_outcome_id)
        if self.conflict is not None:
            raise DecisionReviewIdempotencyConflictError(*self.conflict)
        for review in self.reviews:
            if (
                review.decision_id == values["decision_id"]
                and review.idempotency_key == values["idempotency_key"]
            ):
                return review
        review = DecisionReview.model_validate(
            {**values, "recorded_at": datetime(2026, 7, 18, 14, 0, tzinfo=UTC)}
        )
        self.reviews.append(review)
        return review

    def list_for_decision(self, decision_id: UUID) -> list[DecisionReview]:
        self.list_calls.append(decision_id)
        if self.missing_decision_id is not None:
            raise DecisionReviewDecisionNotFoundError(self.missing_decision_id)
        reviews = [review for review in self.reviews if review.decision_id == decision_id]
        return sorted(reviews, key=lambda item: (item.reviewed_at, str(item.id)))

    def show(self, review_id: UUID) -> DecisionReview:
        self.show_calls.append(review_id)
        for review in self.reviews:
            if review.id == review_id:
                return review
        raise DecisionReviewNotFoundError(review_id)


class ReviewContainer:
    def __init__(self, service: FakeDecisionReviewService) -> None:
        self.service = service

    def decision_review_service(self) -> FakeDecisionReviewService:
        return self.service


def make_review(**updates: object) -> DecisionReview:
    values: dict[str, object] = {
        "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "recorded_at": datetime(2026, 7, 18, 14, 0, tzinfo=UTC),
        "decision_id": UUID("11111111-1111-1111-1111-111111111111"),
        "acceptance_id": UUID("22222222-2222-2222-2222-222222222222"),
        "outcome_ids": (
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
        ),
        "reviewed_by": "architecture-owner",
        "reviewed_at": datetime(2026, 7, 18, 13, 0, tzinfo=UTC),
        "assessment": DecisionReviewAssessment.MIXED,
        "summary": "The evidence supports a mixed assessment.",
        "findings": ("One boundary held.", "One assumption needs validation."),
        "candidate_lessons": ("Validate assumptions explicitly.",),
        "evidence_references": (
            EvidenceReference(kind="agent_review", locator="missing/review.md"),
        ),
        "confidence": DecisionReviewConfidence.HIGH,
        "idempotency_key": "review-cli",
        "tags": ("architecture", "review"),
    }
    values.update(updates)
    return DecisionReview.model_validate(values)


def review_add_args() -> list[str]:
    review = make_review()
    return [
        "decision",
        "review",
        "add",
        str(review.decision_id),
        "--acceptance-id",
        str(review.acceptance_id),
        "--outcome-id",
        str(review.outcome_ids[0]),
        "--outcome-id",
        str(review.outcome_ids[1]),
        "--reviewed-by",
        review.reviewed_by,
        "--reviewed-at",
        review.reviewed_at.isoformat(),
        "--assessment",
        "mixed",
        "--summary",
        review.summary,
        "--finding",
        review.findings[0],
        "--finding",
        review.findings[1],
        "--confidence",
        "high",
        "--idempotency-key",
        review.idempotency_key,
    ]


def test_review_help_exposes_only_add_history_and_show() -> None:
    result = CliRunner().invoke(cli.app, ["decision", "review", "--help"])
    assert result.exit_code == 0
    assert "add" in result.output
    assert "history" in result.output
    assert "show" in result.output
    assert "summary" not in result.output.casefold()


def test_review_add_parses_repeated_values_without_opening_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionReviewService()
    monkeypatch.setattr(cli, "container", ReviewContainer(service))

    def forbidden_open(*args: object, **kwargs: object) -> None:
        raise AssertionError("Evidence locator must not be opened")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    result = CliRunner().invoke(
        cli.app,
        review_add_args()
        + [
            "--candidate-lesson",
            "Validate assumptions explicitly.",
            "--evidence",
            '{"kind":"agent_review","locator":"missing/review.md"}',
            "--tag",
            "architecture",
            "--tag",
            "review",
        ],
    )

    assert result.exit_code == 0
    call = service.add_calls[0]
    assert call["outcome_ids"] == list(make_review().outcome_ids)
    assert call["findings"] == list(make_review().findings)
    assert call["candidate_lessons"] == ["Validate assumptions explicitly."]
    assert call["assessment"] is DecisionReviewAssessment.MIXED
    assert call["confidence"] is DecisionReviewConfidence.HIGH
    assert "Decision review stored." in result.output
    assert "Candidate lessons" in result.output
    assert "kind=agent_review; locator=missing/review.md" in result.output


@pytest.mark.parametrize(
    ("option", "value", "expected_exit"),
    [
        ("--assessment", "succeeded", 2),
        ("--assessment", "reviewed", 2),
        ("--confidence", "certain", 2),
        ("--reviewed-at", "invalid", 1),
    ],
)
def test_review_add_rejects_non_contract_values(
    monkeypatch: pytest.MonkeyPatch, option: str, value: str, expected_exit: int
) -> None:
    service = FakeDecisionReviewService()
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    args = review_add_args()
    args[args.index(option) + 1] = value
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == expected_exit


def test_review_add_has_controlled_relation_and_idempotency_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = make_review()
    service = FakeDecisionReviewService()
    service.missing_decision_id = review.decision_id
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    missing_decision = CliRunner().invoke(cli.app, review_add_args())

    service = FakeDecisionReviewService()
    service.missing_outcome_id = review.outcome_ids[0]
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    missing_outcome = CliRunner().invoke(cli.app, review_add_args())

    service = FakeDecisionReviewService()
    service.conflict = (review.decision_id, review.idempotency_key)
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    conflict = CliRunner().invoke(cli.app, review_add_args())

    assert missing_decision.exit_code == missing_outcome.exit_code == conflict.exit_code == 1
    assert "Decision not found" in missing_decision.output
    assert "Decision outcome not found" in missing_outcome.output
    assert "different payload" in conflict.output


def test_review_add_idempotent_replay_renders_existing_complete_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = make_review()
    service = FakeDecisionReviewService([existing])
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    result = CliRunner().invoke(cli.app, review_add_args())
    assert result.exit_code == 0
    assert str(existing.id) in result.output
    assert "Assessment: mixed" in result.output
    assert service.reviews == [existing]


def test_review_history_is_ordered_and_has_controlled_empty_and_missing_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    later = make_review(id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    earlier = make_review(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        reviewed_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        idempotency_key="earlier",
    )
    service = FakeDecisionReviewService([later, earlier])
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    monkeypatch.setattr(cli, "console", Console(width=240))
    runner = CliRunner()
    history = runner.invoke(cli.app, ["decision", "review", "history", str(later.decision_id)])

    assert history.exit_code == 0
    assert service.list_for_decision(later.decision_id) == [earlier, later]
    assert "Outcome IDs" in history.output
    assert "mixed" in history.output

    service.reviews = []
    empty = runner.invoke(cli.app, ["decision", "review", "history", str(later.decision_id)])
    assert empty.exit_code == 0
    assert "No review history found" in empty.output

    service.missing_decision_id = later.decision_id
    missing = runner.invoke(cli.app, ["decision", "review", "history", str(later.decision_id)])
    assert missing.exit_code == 1
    assert "Decision not found" in missing.output


def test_review_show_renders_every_field_and_missing_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = make_review()
    service = FakeDecisionReviewService([review])
    monkeypatch.setattr(cli, "container", ReviewContainer(service))
    runner = CliRunner()
    shown = runner.invoke(cli.app, ["decision", "review", "show", str(review.id)])

    assert shown.exit_code == 0
    for expected in [
        "Recorded:",
        f"Decision ID: {review.decision_id}",
        f"Acceptance ID: {review.acceptance_id}",
        "Outcome IDs",
        "Reviewed by: architecture-owner",
        "Assessment: mixed",
        "Confidence: high",
        "One boundary held.",
        "Validate assumptions explicitly.",
        "kind=agent_review; locator=missing/review.md",
        "Idempotency key: review-cli",
        "Tags: architecture, review",
    ]:
        assert expected in shown.output

    missing_id = UUID("99999999-9999-9999-9999-999999999999")
    missing = runner.invoke(cli.app, ["decision", "review", "show", str(missing_id)])
    assert missing.exit_code == 1
    assert f"Decision review not found: {missing_id}" in missing.output
